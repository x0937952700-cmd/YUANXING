
import re
from difflib import get_close_matches
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract
from db import get_corrections, get_known_products, log_error

NOISE_WORDS = ["全部筆記", "昨天", "今天", "備忘錄", "新增", "完成", "搜尋", "筆記", "ocr", "key", "掃描文件", "編輯", "返回", "分享", "相簿", "拍照", "上傳", "登入", "登出", "倉庫系統", "智慧倉庫"]

def preprocess_image(image_path):
    try:
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img).convert("L")
        width, height = img.size
        img = img.resize((width * 2, height * 2))
        img = img.filter(ImageFilter.MedianFilter())
        img = ImageEnhance.Contrast(img).enhance(2.3)
        img = ImageEnhance.Sharpness(img).enhance(1.8)
        return img
    except Exception as e:
        log_error("preprocess_image", str(e))
        return Image.open(image_path)

def normalize_text(text):
    text = text.strip()
    for old, new in {" ": "", "×": "x", "X": "x", "：": ":", "O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "（": "(", "）": ")"}.items():
        text = text.replace(old, new)
    return text

def is_noise_line(text):
    t = text.lower()
    if not text.strip():
        return True
    if any(n.lower() in t for n in NOISE_WORDS):
        return True
    if re.match(r"^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}$", text):
        return True
    if re.match(r"^\d{1,2}:\d{2}$", text):
        return True
    if re.match(r"^\d{1,3}$", text):
        return True
    return False

def apply_ai_correction(product_name):
    product_name = normalize_text(product_name)
    corrections = get_corrections()
    if product_name in corrections:
        return corrections[product_name]
    matches = get_close_matches(product_name, get_known_products(), n=1, cutoff=0.72)
    if matches:
        return matches[0]
    return product_name

def parse_line(line):
    line = normalize_text(line)
    for pattern in [r"(.+)[=:](\d+)$", r"(.+)[x](\d+)$", r"(.+)\*(\d+)$", r"(.+)\s+(\d+)$"]:
        m = re.match(pattern, line)
        if m:
            return m.group(1).strip(), int(m.group(2))
    return line, 1

def merge_ocr_lines(raw_data):
    lines = {}
    for i, txt in enumerate(raw_data["text"]):
        text = txt.strip()
        if not text:
            continue
        top = raw_data["top"][i]
        try:
            conf = float(raw_data["conf"][i])
        except Exception:
            conf = 0
        if conf < 10:
            continue
        key = round(top / 12) * 12
        lines.setdefault(key, []).append(text)
    result = []
    for key in sorted(lines.keys()):
        line = "".join(lines[key])
        if not is_noise_line(line):
            result.append(line)
    return result

def process_ocr_text(image_path):
    try:
        img = preprocess_image(image_path)
        raw_data = pytesseract.image_to_data(
            img, lang="chi_tra+eng", config="--psm 6", output_type=pytesseract.Output.DICT
        )
        confs = []
        for c in raw_data["conf"]:
            try:
                v = float(c)
                if v > 0:
                    confs.append(v)
            except Exception:
                pass
        confidence = int(sum(confs) / len(confs)) if confs else 0
        lines = merge_ocr_lines(raw_data)
        items = []
        output = []
        for line in lines:
            if is_noise_line(line):
                continue
            product_raw, qty = parse_line(line)
            if is_noise_line(product_raw):
                continue
            product = apply_ai_correction(product_raw)
            items.append({"raw_text": product_raw, "product_name": product, "product": product, "quantity": qty})
            output.append(f"{product}={qty}")
        return {"success": True, "duplicate": False, "text": "\n".join(output), "lines": output, "items": items, "confidence": confidence}
    except Exception as e:
        log_error("process_ocr_text", str(e))
        return {"success": False, "duplicate": False, "text": "", "lines": [], "items": [], "confidence": 0}
