import re
from collections import defaultdict
from difflib import get_close_matches
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
import pytesseract

from db import get_corrections, list_customers


NOISE_WORDS = [
    "搜尋", "輸入", "辨識", "確認", "上傳", "拍照", "相簿", "返回", "刷新",
    "編輯", "客戶資料", "倉庫圖", "庫存", "總單", "訂單", "出貨", "今日異動"
]


def preprocess_image(image_path):
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("L", "RGB"):
        img = img.convert("RGB")
    gray = img.convert("L")
    # upscale to improve OCR
    if gray.width < 1800:
        ratio = 1800 / float(gray.width)
        gray = gray.resize((1800, int(gray.height * ratio)))
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    gray = ImageEnhance.Contrast(gray).enhance(2.0)
    gray = ImageEnhance.Sharpness(gray).enhance(1.5)
    return gray


def crop_region(img, region=None):
    if not region:
        return img
    try:
        x, y, w, h = [int(v) for v in region]
        x = max(x, 0); y = max(y, 0)
        return img.crop((x, y, x + max(w, 1), y + max(h, 1)))
    except Exception:
        return img


def normalize_text(text):
    mapping = {
        "×": "x", "X": "x", "＊": "*",
        "（": "(", "）": ")",
        "：": ":", "﹕": ":",
        "Ｏ": "0", "o": "0", "O": "0",
        "l": "1", "I": "1", "|": "1",
        "—": "-", "–": "-",
        " ": "",
    }
    text = text.strip()
    for a, b in mapping.items():
        text = text.replace(a, b)
    return text


def is_noise(line):
    if not line or not line.strip():
        return True
    lower = line.lower()
    if any(w.lower() in lower for w in NOISE_WORDS):
        return True
    if re.fullmatch(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", line):
        return True
    return False


def get_known_customers():
    return [c["name"] for c in list_customers()]


def fuzzy_customer_match(name):
    if not name:
        return ""
    candidates = get_known_customers()
    if not candidates:
        return name
    matches = get_close_matches(name, candidates, n=1, cutoff=0.3)
    return matches[0] if matches else name


def apply_corrections(text):
    corrections = get_corrections()
    if text in corrections:
        return corrections[text]
    matches = get_close_matches(text, list(corrections.keys()), n=1, cutoff=0.86)
    if matches:
        return corrections[matches[0]]
    return text


def parse_item_line(line):
    """
    Parse lines like:
    335x46x06 480x6
    130x42x30=96x10
    113*12*05=122*3
    """
    line = normalize_text(line)
    line = line.replace("=", " ")
    line = line.replace("＝", " ")
    line = re.sub(r"[;；,，]", " ", line)
    parts = [p for p in re.split(r"\s+", line) if p]

    # Prefer the first piece with a dimension-like pattern.
    dimension_idx = None
    for i, p in enumerate(parts):
        if re.search(r"\d{2,4}x\d{1,4}x\d{1,4}", p) or re.search(r"\d+[x*]\d+[x*]\d+", p):
            dimension_idx = i
            break
    if dimension_idx is None:
        # fallback
        if len(parts) >= 2:
            return parts[0], parts[1]
        return line, "1"

    product = parts[dimension_idx]
    qty = "1"
    if dimension_idx + 1 < len(parts):
        qty = parts[dimension_idx + 1]
    if re.fullmatch(r"\d+[x*]\d+", qty) is None:
        # if qty isn't obvious, look for trailing number
        m = re.search(r"(\d+[x*]\d+)$", line)
        if m:
            qty = m.group(1)
    return product, qty


def product_to_qty(qty_text):
    if not qty_text:
        return 1
    m = re.match(r"(\d+)[x*](\d+)", qty_text)
    if m:
        return int(m.group(1)) * int(m.group(2))
    m = re.search(r"(\d+)", qty_text)
    return int(m.group(1)) if m else 1


def group_ocr_lines(data):
    lines = defaultdict(list)
    confs = defaultdict(list)
    for i, txt in enumerate(data.get("text", [])):
        txt = (txt or "").strip()
        if not txt:
            continue
        try:
            conf = float(data.get("conf", [0])[i])
        except Exception:
            conf = 0.0
        if conf < 5:
            continue
        top = int(data.get("top", [0])[i])
        line_no = round(top / 12) * 12
        lines[line_no].append(txt)
        confs[line_no].append(conf)
    out = []
    for k in sorted(lines.keys()):
        line = "".join(lines[k])
        if not is_noise(line):
            out.append((line, sum(confs[k]) / max(len(confs[k]), 1)))
    return out


def process_ocr_text(image_path, region=None, customer_keyword=""):
    img = preprocess_image(image_path)
    img = crop_region(img, region)

    raw = pytesseract.image_to_data(img, lang="chi_tra+eng", config="--psm 6", output_type=pytesseract.Output.DICT)
    lines = group_ocr_lines(raw)
    confs = [c for _, c in lines]
    confidence = int(sum(confs) / len(confs)) if confs else 0

    customers = list_customers()
    customer_name_raw = customer_keyword.strip()
    if customer_name_raw:
        customer_name = fuzzy_customer_match(customer_name_raw)
    else:
        # try to discover customer-like tokens from OCR first line
        customer_name = ""
        for line, _ in lines[:3]:
            if re.search(r"[\u4e00-\u9fff]{2,6}", line):
                customer_name = fuzzy_customer_match(re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", line))
                break

    output_lines = []
    items = []
    for line, _ in lines:
        fixed = apply_corrections(normalize_text(line))
        if is_noise(fixed):
            continue
        product, qty_text = parse_item_line(fixed)
        product = apply_corrections(product)
        qty = product_to_qty(qty_text)
        if product:
            items.append({
                "raw_text": line,
                "product_name": product,
                "product": product,
                "quantity": qty,
                "qty_text": qty_text
            })
            output_lines.append(f"{product}={qty}")
    return {
        "success": True,
        "text": "\n".join(output_lines),
        "lines": output_lines,
        "items": items,
        "confidence": confidence,
        "customer_name": customer_name,
        "warning": "辨識信心偏低，請確認內容" if confidence < 80 else ""
    }
