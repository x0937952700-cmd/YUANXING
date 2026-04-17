import re
from difflib import get_close_matches
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract

from db import (
    get_db,
    get_corrections_map,
    log_error,
    get_inventory_snapshot
)

# Windows 可自行指定
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

NOISE_WORDS = [
    "全部筆記", "昨天", "今天", "備忘錄", "新增", "完成", "搜尋", "筆記",
    "ocr", "key", "掃描文件", "編輯", "返回", "分享", "選擇你的方案",
    "plus", "pro", "thinking", "模型", "登入", "logout", "sign in"
]


def preprocess_image(image_path):
    try:
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)
        img = img.convert("L")

        width, height = img.size
        if width < 2000:
            img = img.resize((width * 2, height * 2))

        img = img.filter(ImageFilter.MedianFilter())
        img = ImageEnhance.Contrast(img).enhance(2.2)
        img = ImageEnhance.Sharpness(img).enhance(1.8)
        return img
    except Exception as e:
        log_error("preprocess_image", str(e))
        return Image.open(image_path)


def get_known_products():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT product
            FROM inventory
            WHERE product IS NOT NULL AND product <> ''
        """)
        rows = cur.fetchall()
        conn.close()
        if rows and isinstance(rows[0], dict):
            return [r["product"] for r in rows if r.get("product")]
        return [r[0] for r in rows if r and r[0]]
    except Exception as e:
        log_error("get_known_products", str(e))
        return []


def normalize_text(text):
    text = (text or "").strip()
    replace_map = {
        " ": "",
        "×": "x",
        "X": "x",
        "＊": "x",
        "：": ":",
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "（": "(",
        "）": ")",
        "，": ",",
    }
    for old, new in replace_map.items():
        text = text.replace(old, new)
    return text


def is_noise_line(text):
    text_lower = (text or "").lower()
    if not text.strip():
        return True
    for noise in NOISE_WORDS:
        if noise.lower() in text_lower:
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
    corrections = get_corrections_map()

    if product_name in corrections:
        return corrections[product_name]

    known_products = get_known_products()
    matches = get_close_matches(product_name, known_products, n=1, cutoff=0.72)
    if matches:
        return matches[0]

    return product_name


def parse_line(line):
    line = normalize_text(line)

    patterns = [
        r"(.+)[=:](\d+)$",
        r"(.+)[x](\d+)$",
        r"(.+)\*(\d+)$",
        r"(.+)\s+(\d+)$",
    ]

    for pattern in patterns:
        match = re.match(pattern, line)
        if match:
            product = match.group(1).strip()
            qty = int(match.group(2))
            return product, qty

    return line, 1


def merge_ocr_lines(raw_data):
    lines = {}
    for i in range(len(raw_data["text"])):
        text = str(raw_data["text"][i]).strip()
        if not text:
            continue

        top = raw_data["top"][i]
        conf = raw_data["conf"][i]

        try:
            conf_val = float(conf)
        except Exception:
            conf_val = 0

        if conf_val < 10:
            continue

        row_key = round(top / 12) * 12
        lines.setdefault(row_key, [])
        lines[row_key].append(text)

    result = []
    for row in sorted(lines.keys()):
        line = "".join(lines[row])
        if not is_noise_line(line):
            result.append(line)
    return result


def process_ocr_text(image_path):
    try:
        img = preprocess_image(image_path)

        raw_data = pytesseract.image_to_data(
            img,
            lang="chi_tra+eng",
            config="--psm 6",
            output_type=pytesseract.Output.DICT
        )

        confidence_values = []
        for conf in raw_data["conf"]:
            try:
                val = float(conf)
                if val > 0:
                    confidence_values.append(val)
            except Exception:
                pass

        avg_confidence = 0
        if confidence_values:
            avg_confidence = int(sum(confidence_values) / len(confidence_values))

        raw_lines = merge_ocr_lines(raw_data)

        items = []
        output_lines = []

        for raw_line in raw_lines:
            if is_noise_line(raw_line):
                continue

            product_raw, qty = parse_line(raw_line)
            if is_noise_line(product_raw):
                continue

            product_fixed = apply_ai_correction(product_raw)

            item = {
                "raw_text": product_raw,
                "product_name": product_fixed,
                "product": product_fixed,
                "quantity": qty
            }
            items.append(item)
            output_lines.append(f"{product_fixed}={qty}")

        return {
            "success": True,
            "duplicate": False,
            "text": "\n".join(output_lines),
            "lines": output_lines,
            "items": items,
            "confidence": avg_confidence
        }

    except Exception as e:
        log_error("process_ocr_text", str(e))
        return {
            "success": False,
            "duplicate": False,
            "text": "",
            "lines": [],
            "items": [],
            "confidence": 0
        }
