from __future__ import annotations

import io
import os
import re
from typing import Any

import requests
from PIL import Image, ImageEnhance, ImageFilter

try:
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover
    pytesseract = None


def _blue_text_preprocess(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    width, height = image.size
    image = image.resize((max(width, 1000), int(height * max(width, 1000) / max(width, 1))))
    pixels = image.load()
    for y in range(image.size[1]):
        for x in range(image.size[0]):
            r, g, b = pixels[x, y]
            blueish = b > g + 20 and b > r + 20
            if blueish:
                pixels[x, y] = (0, 0, 0)
            else:
                pixels[x, y] = (255, 255, 255)
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(2.5)
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
        },
        files={"file": ("crop.png", image_bytes)},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    parsed = data.get("ParsedResults") or []
    text = "\n".join((item.get("ParsedText") or "").strip() for item in parsed).strip()
    confidence = 0.0
    return {"text": text, "confidence": confidence, "engine": "ocr.space"}


def _pytesseract_request(image: Image.Image) -> dict[str, Any]:
    if pytesseract is None:
        return {"text": "", "confidence": 0.0, "engine": "none"}
    text = pytesseract.image_to_string(image, lang="chi_tra+eng").strip()
    return {"text": text, "confidence": 0.0, "engine": "pytesseract"}


def parse_text_to_fields(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = " ".join(lines)

    qty = 0
    unit = "件"
    qty_match = re.search(r"(\d+)\s*(件|片|支|包|張|組|條|箱|pcs)?", joined)
    if qty_match:
        qty = int(qty_match.group(1))
        if qty_match.group(2):
            unit = qty_match.group(2)

    customer_name = ""
    product_name = lines[0] if lines else ""
    spec = lines[1] if len(lines) > 1 else ""

    for line in lines:
        if any(key in line for key in ("客戶", "客人", "買家")):
            customer_name = re.sub(r"^(客戶|客人|買家)\s*[:：]?\s*", "", line)
            break

    if not customer_name and len(lines) >= 3:
        customer_name = lines[-1]

    return {
        "customer_name": customer_name,
        "product_name": product_name,
        "spec": spec,
        "quantity": qty,
        "unit": unit,
    }


def run_ocr(file_stream, api_key: str = "") -> dict[str, Any]:
    original_image = Image.open(file_stream)
    processed = _blue_text_preprocess(original_image)

    output = io.BytesIO()
    processed.save(output, format="PNG")
    processed_bytes = output.getvalue()

    result = {"text": "", "confidence": 0.0, "engine": "none"}
    error_message = ""

    if api_key:
        try:
            result = _ocr_space_request(processed_bytes, api_key)
        except Exception as exc:
            error_message = str(exc)

    if not result.get("text"):
        try:
            result = _pytesseract_request(processed)
        except Exception as exc:
            error_message = str(exc)

    hints = []
    if not result.get("text"):
        hints = [
            "重新框選較小的文字區域",
            "盡量只保留藍色手寫或藍色文字",
            "避免反光、陰影與模糊",
            "拍照時讓白板或紙張盡量水平",
            "距離再近一點，讓字體更大更清楚",
        ]

    fields = parse_text_to_fields(result.get("text", ""))

    return {
        "text": result.get("text", "").strip(),
        "confidence": round(float(result.get("confidence", 0.0) or 0.0), 2),
        "engine": result.get("engine", "none"),
        "hints": hints,
        "fields": fields,
        "error_message": error_message,
    }
