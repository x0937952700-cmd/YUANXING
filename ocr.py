# ocr.py
import re
from difflib import get_close_matches
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

import pytesseract

from db import get_db, log_error

# 如果你的伺服器有安裝 tesseract，通常不用改。
# Windows 本機測試可自行指定：
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

NOISE_WORDS = [
    "全部筆記",
    "昨天",
    "今天",
    "備忘錄",
    "新增",
    "完成",
    "搜尋",
    "筆記",
    "ocr",
    "key",
    "掃描文件",
    "編輯",
    "返回",
    "分享",
]

RegionType = Union[Tuple[int, int, int, int], Dict[str, int]]


# =========================================================
# DB helper
# =========================================================
def _rows_to_dicts(cur) -> List[Dict[str, Any]]:
    rows = cur.fetchall()
    if not rows:
        return []

    first = rows[0]
    if hasattr(first, "keys"):
        return [dict(r) for r in rows]

    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in rows]


def get_corrections() -> Dict[str, str]:
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT wrong_text, correct_text FROM corrections")
        rows = _rows_to_dicts(cur)
        conn.close()
        return {
            str(row.get("wrong_text", "")).strip(): str(row.get("correct_text", "")).strip()
            for row in rows
            if row.get("wrong_text")
        }
    except Exception as e:
        log_error("get_corrections", str(e))
        return {}


def get_known_products() -> List[str]:
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT product FROM inventory WHERE product IS NOT NULL")
        rows = _rows_to_dicts(cur)
        conn.close()
        return [
            str(row.get("product", "")).strip()
            for row in rows
            if row.get("product")
        ]
    except Exception as e:
        log_error("get_known_products", str(e))
        return []


# =========================================================
# Text helpers
# =========================================================
def normalize_text(text: str) -> str:
    text = (text or "").strip()

    replace_map = {
        " ": "",
        "×": "x",
        "X": "x",
        "＊": "*",
        "：": ":",
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "（": "(",
        "）": ")",
    }

    for old, new in replace_map.items():
        text = text.replace(old, new)

    return text


def is_noise_line(text: str) -> bool:
    text_lower = (text or "").lower().strip()

    if not text_lower:
        return True

    for noise in NOISE_WORDS:
        if noise.lower() in text_lower:
            return True

    if re.match(r"^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}$", text_lower):
        return True

    if re.match(r"^\d{1,2}:\d{2}$", text_lower):
        return True

    if re.match(r"^\d{1,3}$", text_lower):
        return True

    return False


def apply_ai_correction(product_name: str) -> str:
    product_name = normalize_text(product_name)
    if not product_name:
        return product_name

    corrections = get_corrections()
    if product_name in corrections:
        return corrections[product_name]

    known_products = get_known_products()
    if known_products:
        matches = get_close_matches(product_name, known_products, n=1, cutoff=0.72)
        if matches:
            return matches[0]

    return product_name


def parse_line(line: str) -> Tuple[str, int]:
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


def merge_ocr_lines(raw_data: Dict[str, List[Any]]) -> List[str]:
    lines: Dict[int, List[str]] = {}

    texts = raw_data.get("text", [])
    tops = raw_data.get("top", [])
    confs = raw_data.get("conf", [])

    for i in range(len(texts)):
        text = str(texts[i]).strip()
        if not text:
            continue

        try:
            top = int(float(tops[i]))
        except Exception:
            top = 0

        try:
            conf_val = float(confs[i])
        except Exception:
            conf_val = 0

        if conf_val < 10:
            continue

        row_key = round(top / 12) * 12
        lines.setdefault(row_key, []).append(text)

    result = []
    for row in sorted(lines.keys()):
        line = "".join(lines[row]).strip()
        if line and not is_noise_line(line):
            result.append(line)

    return result


# =========================================================
# Image preprocess
# =========================================================
def _parse_region(region: Optional[RegionType], image_size: Tuple[int, int]) -> Optional[Tuple[int, int, int, int]]:
    if not region:
        return None

    w, h = image_size

    if isinstance(region, tuple) and len(region) == 4:
        x1, y1, x2, y2 = region
        x1 = max(0, min(w, int(x1)))
        y1 = max(0, min(h, int(y1)))
        x2 = max(0, min(w, int(x2)))
        y2 = max(0, min(h, int(y2)))
        if x2 <= x1 or y2 <= y1:
            return None
        return (x1, y1, x2, y2)

    if isinstance(region, dict):
        if {"x", "y", "w", "h"}.issubset(region.keys()):
            x1 = int(region["x"])
            y1 = int(region["y"])
            x2 = x1 + int(region["w"])
            y2 = y1 + int(region["h"])
        elif {"left", "top", "right", "bottom"}.issubset(region.keys()):
            x1 = int(region["left"])
            y1 = int(region["top"])
            x2 = int(region["right"])
            y2 = int(region["bottom"])
        else:
            return None

        x1 = max(0, min(w, x1))
        y1 = max(0, min(h, y1))
        x2 = max(0, min(w, x2))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            return None
        return (x1, y1, x2, y2)

    return None


def _keep_only_blue_text(img: Image.Image) -> Image.Image:
    """
    只保留偏藍色字體，其他都變白。
    這是用純 Pillow 做的，不需要 OpenCV。
    """
    rgb = img.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size

    out = Image.new("RGB", (width, height), (255, 255, 255))
    out_pixels = out.load()

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]

            # 藍色優先判斷：藍通道明顯高於紅綠
            is_blue = (
                b >= 70 and
                b >= r + 18 and
                b >= g + 10 and
                (b - ((r + g) // 2)) >= 15
            )

            if is_blue:
                out_pixels[x, y] = (0, 0, 0)
            else:
                out_pixels[x, y] = (255, 255, 255)

    return out


def preprocess_image(
    image_path: str,
    region: Optional[RegionType] = None,
    only_blue: bool = True,
) -> Image.Image:
    try:
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)

        crop_box = _parse_region(region, img.size)
        if crop_box:
            img = img.crop(crop_box)

        # 藍字優先：只保留藍色字體
        if only_blue:
            img = _keep_only_blue_text(img)

        # 灰階
        img = img.convert("L")

        # 放大，提升 OCR 率
        width, height = img.size
        if width < 1600:
            scale = 1600 / float(width)
            img = img.resize((1600, max(1, int(height * scale))))

        # 降噪 / 增強 / 銳化
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = ImageEnhance.Contrast(img).enhance(2.4)
        img = ImageEnhance.Sharpness(img).enhance(1.8)

        return img

    except Exception as e:
        log_error("preprocess_image", str(e))
        try:
            return Image.open(image_path)
        except Exception as e2:
            log_error("preprocess_image_fallback", str(e2))
            raise


# =========================================================
# Main OCR
# =========================================================
def process_ocr_text(
    image_path: str,
    region: Optional[RegionType] = None,
    only_blue: bool = True,
) -> Dict[str, Any]:
    """
    - 支援區域辨識
    - 支援只辨識藍色字體
    - 沒有 OpenCV 也能跑
    - 信心值低也會正常回傳 text/items，讓前端繼續顯示與手動修正
    """
    try:
        img = preprocess_image(image_path, region=region, only_blue=only_blue)

        raw_data = pytesseract.image_to_data(
            img,
            lang="chi_tra+eng",
            config="--psm 6",
            output_type=pytesseract.Output.DICT,
        )

        confidence_values = []
        for conf in raw_data.get("conf", []):
            try:
                val = float(conf)
                if val > 0:
                    confidence_values.append(val)
            except Exception:
                pass

        avg_confidence = int(sum(confidence_values) / len(confidence_values)) if confidence_values else 0

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
                "quantity": qty,
            }
            items.append(item)
            output_lines.append(f"{product_fixed}={qty}")

        return {
            "success": True,
            "duplicate": False,
            "text": "\n".join(output_lines),
            "lines": output_lines,
            "items": items,
            "confidence": avg_confidence,
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
            "error": "OCR辨識失敗",
        }