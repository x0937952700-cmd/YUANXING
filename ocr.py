import re
from difflib import get_close_matches
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import pytesseract

from db import get_corrections, get_known_products, log_error

NOISE_WORDS = [
    '全部筆記', '昨天', '今天', '備忘錄', '新增', '完成', '搜尋', '筆記', 'ocr', 'key',
    '掃描文件', '編輯', '返回', '分享', '設定', '登入', '倉庫', '出貨', '訂單'
]


def preprocess_image(image_path):
    try:
        img = Image.open(image_path)
        img = ImageOps.exif_transpose(img)
        img = img.convert('L')
        w, h = img.size
        if w < 1400:
            img = img.resize((w * 2, h * 2))
        img = img.filter(ImageFilter.MedianFilter())
        img = ImageEnhance.Contrast(img).enhance(2.4)
        img = ImageEnhance.Sharpness(img).enhance(1.8)
        return img
    except Exception as e:
        log_error('preprocess_image', e)
        return Image.open(image_path)


def normalize_text(text):
    text = (text or '').strip()
    replace_map = {
        ' ': '', '×': 'x', 'X': 'x', '：': ':', '（': '(', '）': ')',
        'O': '0', 'o': '0', 'I': '1', 'l': '1', '|': '1', '—': '-', '–': '-',
    }
    for a, b in replace_map.items():
        text = text.replace(a, b)
    return text


def is_noise_line(text):
    t = (text or '').strip().lower()
    if not t:
        return True
    for noise in NOISE_WORDS:
        if noise.lower() in t:
            return True
    if re.match(r'^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}$', t):
        return True
    if re.match(r'^\d{1,2}:\d{2}$', t):
        return True
    if re.match(r'^\d{1,3}$', t):
        return True
    return False


def apply_ai_correction(product_name):
    product_name = normalize_text(product_name)
    corrections = get_corrections()
    if product_name in corrections:
        return corrections[product_name]

    # partial replacements from learned corrections
    for wrong, correct in corrections.items():
        if wrong and wrong in product_name:
            product_name = product_name.replace(wrong, correct)

    known_products = get_known_products()
    matches = get_close_matches(product_name, known_products, n=1, cutoff=0.72)
    if matches:
        return matches[0]
    return product_name


def parse_line(line):
    line = normalize_text(line)
    patterns = [
        r'(.+)[=:](\d+)$',
        r'(.+)[x](\d+)$',
        r'(.+)\*(\d+)$',
        r'(.+)\s+(\d+)$',
    ]
    for pattern in patterns:
        m = re.match(pattern, line)
        if m:
            return m.group(1).strip(), int(m.group(2))
    return line, 1


def merge_ocr_lines(raw_data):
    lines = {}
    for i in range(len(raw_data['text'])):
        text = (raw_data['text'][i] or '').strip()
        if not text:
            continue
        top = raw_data['top'][i]
        conf = raw_data['conf'][i]
        try:
            conf_val = float(conf)
        except Exception:
            conf_val = 0
        if conf_val < 10:
            continue
        row_key = round(top / 12) * 12
        lines.setdefault(row_key, []).append(text)

    result = []
    for row in sorted(lines):
        line = ''.join(lines[row])
        if not is_noise_line(line):
            result.append(line)
    return result


def process_ocr_text(image_path):
    try:
        img = preprocess_image(image_path)
        raw_data = pytesseract.image_to_data(
            img,
            lang='chi_tra+eng',
            config='--psm 6',
            output_type=pytesseract.Output.DICT,
        )

        confs = []
        for conf in raw_data.get('conf', []):
            try:
                v = float(conf)
                if v > 0:
                    confs.append(v)
            except Exception:
                pass
        avg_confidence = int(sum(confs) / len(confs)) if confs else 0

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
            items.append({
                'raw_text': product_raw,
                'product_name': product_fixed,
                'product': product_fixed,
                'quantity': qty,
            })
            output_lines.append(f'{product_fixed}={qty}')

        return {
            'success': True,
            'duplicate': False,
            'text': '\n'.join(output_lines),
            'lines': output_lines,
            'items': items,
            'confidence': avg_confidence,
        }
    except Exception as e:
        log_error('process_ocr_text', e)
        return {
            'success': False,
            'duplicate': False,
            'text': '',
            'lines': [],
            'items': [],
            'confidence': 0,
        }
