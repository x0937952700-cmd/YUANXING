from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import timedelta
from pathlib import Path
import os
import io
import hashlib
import threading
import time

from PIL import Image

from db import (
    init_db,
    get_user,
    create_user,
    log_action,
    save_inventory,
    save_order,
    save_master_order,
    ship_order,
    get_shipping_records,
    save_correction,
    find_multiple_locations,
    log_error,
    save_image_hash,
    image_hash_exists,
    get_inventory_snapshot,
    get_orders_snapshot,
    get_master_orders_snapshot,
    get_logs_snapshot,
)
from ocr import process_ocr_text
from backup import run_daily_backup, list_backups

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "warehouse-secret-key")
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER = Path("uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "bmp"}
MAX_UPLOAD_SIZE = 16 * 1024 * 1024
AUTO_BACKUP_ENABLED = os.getenv("AUTO_BACKUP_ENABLED", "1") != "0"

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE

init_db()


# =====================================
# 工具
# =====================================
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def require_login() -> bool:
    return "user" in session


def error_response(msg, code=400):
    return jsonify({"success": False, "error": msg}), code


def get_payload():
    data = request.get_json(silent=True)
    if isinstance(data, dict):
        return data
    return request.form.to_dict(flat=True)


def parse_items_from_payload(payload):
    """
    接受：
    1) items: [{product, quantity, location?}]
    2) text: OCR 多行文字
    """
    items = payload.get("items")
    if isinstance(items, list) and items:
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            product = str(item.get("product", "")).strip()
            qty = item.get("quantity", 0)
            location = str(item.get("location", "")).strip()
            if not product:
                continue
            try:
                qty = int(qty)
            except Exception:
                qty = 0
            if qty <= 0:
                continue
            normalized.append({
                "product": product,
                "quantity": qty,
                "location": location
            })
        if normalized:
            return normalized

    text = str(payload.get("text", "")).strip()
    if not text:
        return []

    result = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # 支援：A=2 / Ax2 / A X 2 / A:2
        product = line
        qty = 1

        separators = ["=", "x", "X", "＊", "*", ":"]
        for sep in separators:
            if sep in line:
                left, right = line.rsplit(sep, 1)
                if left.strip() and right.strip().isdigit():
                    product = left.strip()
                    qty = int(right.strip())
                    break

        # 支援：商品 2
        if qty == 1:
            parts = line.split()
            if len(parts) >= 2 and parts[-1].isdigit():
                qty = int(parts[-1])
                product = " ".join(parts[:-1]).strip()

        if product and qty > 0:
            result.append({"product": product, "quantity": qty, "location": ""})

    return result


def compress_image_bytes(image_bytes: bytes, max_width: int = 1600, quality: int = 82) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    if img.width > max_width:
        ratio = max_width / float(img.width)
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def save_uploaded_image(file_storage):
    content = file_storage.read()
    image_hash = hashlib.md5(content).hexdigest()

    if image_hash_exists(image_hash):
        return None, image_hash, "duplicate"

    try:
        compressed = compress_image_bytes(content)
    except Exception as e:
        log_error("compress_image_bytes", str(e))
        return None, image_hash, "compress_error"

    filename = f"{image_hash}.jpg"
    path = UPLOAD_FOLDER / filename

    with open(path, "wb") as f:
        f.write(compressed)

    save_image_hash(image_hash)
    return path, image_hash, "ok"


def startup_backup_loop():
    while True:
        if not AUTO_BACKUP_ENABLED:
            return
        # 每 24 小時做一次；第一次啟動後先等 10 分鐘，避免部署瞬間觸發
        time.sleep(600)
        try:
            run_daily_backup()
        except Exception as e:
            log_error("startup_backup_loop", str(e))
        time.sleep(24 * 60 * 60 - 600)


def start_background_tasks():
    if AUTO_BACKUP_ENABLED:
        t = threading.Thread(target=startup_backup_loop, daemon=True)
        t.start()


start_background_tasks()


# =====================================
# 頁面
# =====================================
@app.route("/")
def home():
    if not require_login():
        return redirect(url_for("login_page"))
    return render_template("index.html")


@app.route("/login")
def login_page():
    if require_login():
        return redirect(url_for("home"))
    return render_template("login.html")


# =====================================
# Session
# =====================================
@app.route("/api/session")
def api_session():
    return jsonify({
        "success": True,
        "authenticated": require_login(),
        "user": session.get("user", "")
    })


# =====================================
# 登入 / 登出
# =====================================
@app.route("/api/login", methods=["POST"])
def login():
    try:
        payload = get_payload()
        username = str(payload.get("username") or payload.get("name") or "").strip()
        password = str(payload.get("password") or "").strip()

        if not username or not password:
            return error_response("帳號密碼不可空白")

        user = get_user(username)

        if not user:
            create_user(username, password)
            log_action(username, "建立帳號")
        elif user.get("password") != password:
            return error_response("密碼錯誤")

        session.permanent = True
        session["user"] = username
        log_action(username, "登入系統")

        return jsonify({"success": True, "username": username})
    except Exception as e:
        log_error("login", str(e))
        return error_response("登入失敗", 500)


@app.route("/api/logout", methods=["POST"])
def logout():
    user = session.get("user", "")
    session.clear()
    if user:
        log_action(user, "登出系統")
    return jsonify({"success": True})


# =====================================
# OCR
# =====================================
@app.route("/api/upload_ocr", methods=["POST"])
def upload_ocr():
    try:
        if not require_login():
            return error_response("請先登入", 401)

        file = request.files.get("file") or request.files.get("image")
        if not file:
            return error_response("未選擇圖片")

        if not allowed_file(file.filename):
            return error_response("圖片格式錯誤")

        path, image_hash, status = save_uploaded_image(file)
        if status == "duplicate":
            return error_response("此圖片已上傳過")
        if status != "ok" or path is None:
            return error_response("圖片處理失敗")

        result = process_ocr_text(str(path))
        if not result.get("success"):
            return error_response("OCR辨識失敗")

        items = result.get("items", [])
        locations = find_multiple_locations([item.get("product", "") for item in items if item.get("product")])

        confidence = int(result.get("confidence", 0))

        log_action(session["user"], "OCR辨識")

        return jsonify({
            "success": True,
            "text": result.get("text", ""),
            "lines": result.get("lines", []),
            "items": items,
            "confidence": confidence,
            "warning": "辨識信心偏低，請確認內容" if confidence < 80 else "",
            "locations": locations,
            "sync_time": int(path.stat().st_mtime),
        })
    except Exception as e:
        log_error("upload_ocr", str(e))
        return error_response("OCR辨識失敗", 500)


# =====================================
# AI 修正
# =====================================
@app.route("/api/save_correction", methods=["POST"])
def api_save_correction():
    try:
        if not require_login():
            return error_response("請先登入", 401)

        payload = get_payload()
        wrong = str(payload.get("wrong_text", "")).strip()
        correct = str(payload.get("correct_text", "")).strip()

        if wrong and correct and wrong != correct:
            save_correction(wrong, correct)
            log_action(session["user"], f"修正OCR {wrong}->{correct}")

        return jsonify({"success": True})
    except Exception as e:
        log_error("save_correction", str(e))
        return error_response("儲存失敗", 500)


# =====================================
# 庫存 / 訂單 / 總單 / 出貨
# =====================================
@app.route("/api/inventory", methods=["POST"])
def api_inventory():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        payload = get_payload()
        items = parse_items_from_payload(payload)
        if not items:
            return error_response("沒有可新增的商品")
        for item in items:
            item["operator"] = session["user"]
            save_inventory(item)
        log_action(session["user"], "建立庫存")
        return jsonify({"success": True})
    except Exception as e:
        log_error("inventory", str(e))
        return error_response("建立失敗", 500)


@app.route("/api/order", methods=["POST"])
def api_order():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        payload = get_payload()
        customer = str(payload.get("customer", "")).strip()
        items = parse_items_from_payload(payload)
        if not customer:
            return error_response("客戶名稱不可空白")
        if not items:
            return error_response("沒有可建立的訂單")
        save_order(customer, items, session["user"])
        log_action(session["user"], f"建立訂單 {customer}")
        return jsonify({"success": True})
    except Exception as e:
        log_error("order", str(e))
        return error_response("訂單建立失敗", 500)


@app.route("/api/master_order", methods=["POST"])
def api_master():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        payload = get_payload()
        customer = str(payload.get("customer", "")).strip()
        items = parse_items_from_payload(payload)
        if not customer:
            return error_response("客戶名稱不可空白")
        if not items:
            return error_response("沒有可更新的總單")
        save_master_order(customer, items, session["user"])
        log_action(session["user"], f"更新總單 {customer}")
        return jsonify({"success": True})
    except Exception as e:
        log_error("master_order", str(e))
        return error_response("總單失敗", 500)


@app.route("/api/ship", methods=["POST"])
def api_ship():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        payload = get_payload()
        customer = str(payload.get("customer", "")).strip()
        items = parse_items_from_payload(payload)
        if not customer:
            return error_response("客戶名稱不可空白")
        if not items:
            return error_response("沒有可出貨的商品")

        result = ship_order(customer, items, session["user"])
        if result.get("success"):
            log_action(session["user"], f"完成出貨 {customer}")
        return jsonify(result)
    except Exception as e:
        log_error("ship", str(e))
        return error_response("出貨失敗", 500)


# =====================================
# 查詢
# =====================================
@app.route("/api/shipping_records")
def api_shipping():
    return jsonify({"success": True, "records": get_shipping_records()})


@app.route("/api/inventory/list")
def api_inventory_list():
    return jsonify({"success": True, "items": get_inventory_snapshot()})


@app.route("/api/orders/list")
def api_orders_list():
    return jsonify({"success": True, "items": get_orders_snapshot()})


@app.route("/api/master_orders/list")
def api_master_orders_list():
    return jsonify({"success": True, "items": get_master_orders_snapshot()})


@app.route("/api/logs")
def api_logs():
    return jsonify({"success": True, "items": get_logs_snapshot()})


@app.route("/api/find_locations", methods=["POST"])
def api_find_locations():
    try:
        payload = get_payload()
        items = payload.get("items", [])
        if not isinstance(items, list):
            items = []
        return jsonify({"success": True, "items": find_multiple_locations(items)})
    except Exception as e:
        log_error("find_locations", str(e))
        return error_response("定位失敗", 500)


# =====================================
# 備份
# =====================================
@app.route("/api/backup")
def api_backup():
    return jsonify(run_daily_backup())


@app.route("/api/backups")
def api_backups():
    return jsonify(list_backups())


# =====================================
# 健康檢查
# =====================================
@app.route("/health")
def health():
    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
