
import re
from difflib import get_close_matches
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract

from db import get_corrections, list_customers, list_inventory, log_error


def preprocess_image(image_path, region=None, blue_only=True):
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    if region:
        try:
            x, y, w, h = [int(v) for v in region]
            img = img.crop((x, y, x + w, y + h))
        except Exception:
            pass
    rgb = img.convert("RGB")
    arr = np.array(rgb)

    if blue_only:
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        lower = np.array([90, 40, 40])
        upper = np.array([150, 255, 255])
        mask = cv2.inRange(hsv, lower, upper)
        if mask.sum() > 0:
            arr = cv2.bitwise_and(arr, arr, mask=mask)
            gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
            gray = cv2.bitwise_not(gray)
            pil = Image.fromarray(gray)
        else:
            pil = rgb.convert("L")
    else:
        pil = rgb.convert("L")

    width, height = pil.size
    if width < 1200:
        pil = pil.resize((width * 2, height * 2))
    pil = pil.filter(ImageFilter.MedianFilter())
    pil = ImageEnhance.Contrast(pil).enhance(2.2)
    pil = ImageEnhance.Sharpness(pil).enhance(1.6)
    return pil


def normalize_text(text):
    text = (text or "").strip()
    replace_map = {
        "×": "x",
        "X": "x",
        "＊": "*",
        "﹡": "*",
        "，": ",",
        "：": ":",
        "／": "/",
        "（": "(",
        "）": ")",
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        " ": "",
    }
    for a, b in replace_map.items():
        text = text.replace(a, b)
    return text


NOISE_WORDS = ["全部筆記", "昨天", "今天", "備忘錄", "新增", "完成", "搜尋", "筆記", "ocr", "掃描文件", "編輯", "返回", "分享"]


def is_noise_line(text):
    t = (text or "").strip()
    if not t:
        return True
    low = t.lower()
    for noise in NOISE_WORDS:
        if noise.lower() in low:
            return True
    if re.match(r"^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}$", t):
        return True
    if re.match(r"^\d{1,2}:\d{2}$", t):
        return True
    return False


def apply_corrections(text):
    text = normalize_text(text)
    corrections = get_corrections()
    for wrong, correct in corrections.items():
        if wrong and wrong in text:
            text = text.replace(wrong, correct)
    # fuzzy product correction
    known_products = [r["product"] for r in list_inventory()]
    if known_products:
        matches = get_close_matches(text, known_products, n=1, cutoff=0.74)
        if matches:
            text = matches[0]
    return text


def parse_line(line):
    line = normalize_text(line)
    patterns = [
        r"(.+)[=:](\d+)$",
        r"(.+)[x\*](\d+)$",
        r"(.+)\s+(\d+)$",
    ]
    for pattern in patterns:
        m = re.match(pattern, line)
        if m:
            return m.group(1).strip(), int(m.group(2))
    return line, 1


def customer_match(name):
    name = normalize_text(name)
    customers = [c["customer_name"] for c in list_customers()]
    if not customers:
        return name
    if name in customers:
        return name
    matches = get_close_matches(name, customers, n=1, cutoff=0.42)
    if matches:
        return matches[0]
    # prefix fallback
    for c in customers:
        if name and name in c:
            return c
    return name


def process_ocr_text(image_path, region=None, blue_only=True):
    try:
        img = preprocess_image(image_path, region=region, blue_only=blue_only)
        raw_data = pytesseract.image_to_data(
            img,
            lang="chi_tra+eng",
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
        )

        confs = []
        for c in raw_data.get("conf", []):
            try:
                val = float(c)
                if val > 0:
                    confs.append(val)
            except Exception:
                pass
        avg_conf = int(sum(confs) / len(confs)) if confs else 0

        rows = {}
        for i, txt in enumerate(raw_data.get("text", [])):
            txt = (txt or "").strip()
            if not txt:
                continue
            try:
                conf = float(raw_data["conf"][i])
            except Exception:
                conf = 0
            if conf < 10:
                continue
            top = int(raw_data["top"][i])
            key = round(top / 12) * 12
            rows.setdefault(key, []).append(txt)

        raw_lines = []
        for k in sorted(rows.keys()):
            line = "".join(rows[k])
            if not is_noise_line(line):
                raw_lines.append(line)

        items = []
        output_lines = []
        for raw_line in raw_lines:
            raw_line = normalize_text(raw_line)
            if is_noise_line(raw_line):
                continue
            product_raw, qty = parse_line(raw_line)
            product_fixed = apply_corrections(product_raw)
            items.append({
                "raw_text": product_raw,
                "product_name": product_fixed,
                "product": product_fixed,
                "quantity": qty,
            })
            output_lines.append(f"{product_fixed}={qty}")

        # If nothing found, at least give a safe empty result
        return {
            "success": True,
            "duplicate": False,
            "text": "\n".join(output_lines),
            "lines": output_lines,
            "items": items,
            "confidence": avg_conf,
            "warning": "辨識信心偏低，請確認內容" if avg_conf and avg_conf < 80 else "",
            "customer_guess": customer_match(output_lines[0].split("=")[0] if output_lines else ""),
        }
    except Exception as e:
        log_error("process_ocr_text", str(e))
        return {
            "success": False,
            "duplicate": False,
            "text": "",
            "lines": [],
            "items": [],
            "confidence": 0,
            "warning": "OCR辨識失敗",
            "customer_guess": "",
        }
