
import re
from difflib import get_close_matches
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from db import get_db, log_error, get_corrections, list_inventory

try:
    import pytesseract
except Exception:
    pytesseract = None

NOISE_WORDS = [
    "全部筆記", "昨天", "今天", "備忘錄", "新增", "完成", "搜尋",
    "筆記", "ocr", "key", "掃描文件", "編輯", "返回", "分享"
]

def _focus_blue_pixels(img):
    """盡量只保留藍色字體，降低紅色/綠色/背景雜訊干擾。"""
    try:
        rgb = img.convert("RGB")
        width, height = rgb.size
        pix = rgb.load()
        min_x, min_y = width, height
        max_x, max_y = 0, 0
        found = False
        out = Image.new("RGB", (width, height), "white")
        out_pix = out.load()
        for y in range(height):
            for x in range(width):
                r, g, b = pix[x, y]
                if b > r + 20 and b > g + 8 and b > 60:
                    found = True
                    out_pix[x, y] = (0, 0, 0)
                    if x < min_x: min_x = x
                    if y < min_y: min_y = y
                    if x > max_x: max_x = x
                    if y > max_y: max_y = y
        if found and max_x > min_x and max_y > min_y:
            pad = 18
            box = (max(0, min_x - pad), max(0, min_y - pad), min(width, max_x + pad), min(height, max_y + pad))
            return out.crop(box)
        return img.convert("L")
    except Exception:
        return img.convert("L")

def preprocess_image(image_path):
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    img = _focus_blue_pixels(img)
    img = img.convert("L")
    width, height = img.size
    if width < 1200:
        img = img.resize((width * 2, height * 2))
    img = img.filter(ImageFilter.MedianFilter())
    img = ImageEnhance.Contrast(img).enhance(2.4)
    img = ImageEnhance.Sharpness(img).enhance(1.9)
    return img

def normalize_text(text):
    text = (text or "").strip()
    replace_map = {
        " ": "",
        "×": "x",
        "X": "x",
        "：": ":",
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "（": "(",
        "）": ")",
        "＊": "*",
        "﹡": "*",
    }
    for old, new in replace_map.items():
        text = text.replace(old, new)
    return text

def is_noise_line(text):
    low = text.lower()
    if not text.strip():
        return True
    for noise in NOISE_WORDS:
        if noise.lower() in low:
            return True
    if re.match(r"^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}$", text):
        return True
    if re.match(r"^\d{1,2}:\d{2}$", text):
        return True
    if re.match(r"^\d{1,3}$", text):
        return True
    return False

def get_known_products():
    rows = list_inventory()
    return [r["product_text"] for r in rows if r.get("product_text")]

def apply_ai_correction(product_name):
    product_name = normalize_text(product_name)
    corrections = get_corrections()
    if product_name in corrections:
        return corrections[product_name]
    known_products = get_known_products()
    if known_products:
        matches = get_close_matches(product_name, known_products, n=1, cutoff=0.72)
        if matches:
            return matches[0]
    return product_name

def parse_line(line):
    line = normalize_text(line)
    # split on = or : then quantity
    patterns = [
        r"(.+?)[=:](\d+)$",
        r"(.+?)[x](\d+)$",
        r"(.+?)\*(\d+)$",
        r"(.+?)\s+(\d+)$",
    ]
    for p in patterns:
        m = re.match(p, line)
        if m:
            return m.group(1).strip(), int(m.group(2))
    return line, 1

def parse_ocr_text(text):
    lines = []
    items = []
    for raw in (text or "").splitlines():
        raw = raw.strip()
        if not raw or is_noise_line(raw):
            continue
        product_raw, qty = parse_line(raw)
        if is_noise_line(product_raw):
            continue
        product_fixed = apply_ai_correction(product_raw)
        items.append({
            "raw_text": product_raw,
            "product_text": product_fixed,
            "product_code": product_fixed.split("=")[0],
            "qty": qty
        })
        lines.append(f"{product_fixed}={qty}")
    return {
        "text": "\n".join(lines),
        "lines": lines,
        "items": items
    }

def process_ocr_text(image_path):
    try:
        if pytesseract is None:
            return {"success": False, "duplicate": False, "text": "", "lines": [], "items": [], "confidence": 0}
        img = preprocess_image(image_path)
        confidence_values = []
        try:
            raw_data = pytesseract.image_to_data(
                img,
                lang="chi_tra+eng",
                config="--psm 6",
                output_type=pytesseract.Output.DICT
            )
            for conf in raw_data.get("conf", []):
                try:
                    val = float(conf)
                    if val > 0:
                        confidence_values.append(val)
                except Exception:
                    pass
        except Exception:
            raw_data = {}
        avg_confidence = int(sum(confidence_values) / len(confidence_values)) if confidence_values else 0

        # 先用藍字強化圖，如果結果太少再用原圖備援
        texts = []
        original = ImageOps.exif_transpose(Image.open(image_path)).convert("L")
        for candidate in [img, original]:
            try:
                texts.append(pytesseract.image_to_string(candidate, lang="chi_tra+eng", config="--psm 6"))
            except Exception:
                continue
        text = next((t for t in texts if t and t.strip()), "")
        parsed = parse_ocr_text(text)
        return {
            "success": True,
            "duplicate": False,
            "text": parsed["text"],
            "lines": parsed["lines"],
            "items": parsed["items"],
            "confidence": avg_confidence
        }
    except Exception as e:
        log_error("process_ocr_text", e)
        return {"success": False, "duplicate": False, "text": "", "lines": [], "items": [], "confidence": 0}
