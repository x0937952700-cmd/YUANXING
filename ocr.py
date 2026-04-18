import io
import os
import re
from typing import Any

import requests
from PIL import Image, ImageEnhance, ImageFilter

try:
    import pytesseract  # type: ignore
except Exception:
    pytesseract = None

from db import get_corrections


def _blue_text_preprocess(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    width, height = image.size
    target_w = max(min(width, 1800), 1000)
    target_h = int(height * target_w / max(width, 1))
    image = image.resize((target_w, target_h))
    pixels = image.load()
    for y in range(image.size[1]):
        for x in range(image.size[0]):
            r, g, b = pixels[x, y]
            blueish = b > g + 18 and b > r + 18
            if blueish:
                pixels[x, y] = (0, 0, 0)
            else:
                pixels[x, y] = (255, 255, 255)
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(2.6)
    image = image.filter(ImageFilter.SHARPEN)
    return image


def _ocr_space_request(image_bytes: bytes, api_key: str) -> dict[str, Any]:
    response = requests.post(
        "https://api.ocr.space/parse/image",
        data={
            "apikey": api_key,
            "language": "cht",
            "isOverlayRequired": False,
            "OCREngine": 2,
            "scale": True,
            "detectOrientation": True,
        },
        files={"file": ("crop.png", image_bytes)},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("IsErroredOnProcessing"):
        msg = "; ".join(data.get("ErrorMessage") or data.get("ErrorDetails") or ["OCR.Space 處理失敗"])
        raise RuntimeError(msg)
    parsed = data.get("ParsedResults") or []
    text = "\n".join((item.get("ParsedText") or "").strip() for item in parsed).strip()
    return {"text": text, "confidence": 88.0 if text else 0.0, "engine": "ocr.space"}


def _pytesseract_request(image: Image.Image) -> dict[str, Any]:
    if pytesseract is None:
        return {"text": "", "confidence": 0.0, "engine": "none"}
    text = pytesseract.image_to_string(image, lang="chi_tra+eng").strip()
    confidence = 58.0 if text else 0.0
    return {"text": text, "confidence": confidence, "engine": "pytesseract"}


def _apply_corrections(text: str) -> str:
    corrections = get_corrections()
    for wrong, correct in corrections.items():
        text = text.replace(wrong, correct)
    return text


def parse_ocr_text(text: str) -> dict[str, Any]:
    text = _apply_corrections(text or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items = []
    for line in lines:
        m = re.search(r"(.+?)\s+(\d+)\s*(件|片|支|包|張|組|條|箱|pcs)?$", line)
        if m:
            items.append({
                "product_text": m.group(1).strip(),
                "qty": int(m.group(2)),
                "unit": m.group(3) or "件",
                "product_code": "",
            })
    if not items and lines:
        qty_match = re.search(r"(\d+)", text)
        qty = int(qty_match.group(1)) if qty_match else 1
        items = [{"product_text": lines[0], "qty": qty, "unit": "件", "product_code": ""}]
    return {"text": "\n".join(lines), "items": items}


def process_ocr_text(path: str) -> dict[str, Any]:
    api_key = os.getenv("OCR_SPACE_API_KEY", "").strip()
    original_image = Image.open(path)
    processed = _blue_text_preprocess(original_image)
    output = io.BytesIO()
    processed.save(output, format="PNG")
    processed_bytes = output.getvalue()

    result = {"text": "", "confidence": 0.0, "engine": "none"}
    hints = []
    warning = ""

    if api_key:
        try:
            result = _ocr_space_request(processed_bytes, api_key)
        except Exception as exc:
            warning = f"OCR API 失敗，已改用備援辨識：{exc}"

    if not result.get("text"):
        try:
            result = _pytesseract_request(processed)
        except Exception as exc:
            warning = f"本機辨識失敗：{exc}"

    text = _apply_corrections((result.get("text") or "").strip())
    parsed = parse_ocr_text(text)

    if not text:
        warning = warning or "辨識失敗，請手動編輯"
        hints = [
            "到 Render 服務的 Environment 加入 OCR_SPACE_API_KEY",
            "上傳後先框選較小的文字區域再辨識",
            "優先拍藍色字，避免陰影與反光",
            "畫面模糊時請靠近一點再拍",
            "若還是失敗，辨識文字框可直接手動修改後送出",
        ]
    elif (result.get("confidence") or 0) < 80:
        warning = warning or "辨識信心偏低，請確認內容"

    return {
        "success": True,
        "text": parsed.get("text", text),
        "items": parsed.get("items", []),
        "confidence": int(result.get("confidence", 0) or 0),
        "engine": result.get("engine", "none"),
        "warning": warning,
        "hints": hints,
    }
