
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import timedelta
import hashlib
import os
from PIL import Image

from db import (
    init_db, get_user, create_user, update_user_password, log_action, save_inventory,
    save_order, save_master_order, ship_order, get_shipping_records, save_correction,
    find_multiple_locations, log_error, save_image_hash, image_hash_exists,
    list_customers, get_customer, save_customer, seed_default_customers,
    list_warehouse_slots, save_warehouse_slot, delete_warehouse_slot,
    get_settings, set_setting
)
from ocr import process_ocr_text
from backup import run_daily_backup, list_backups

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "warehouse-secret-key")
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_UPLOAD_SIZE = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE

init_db()
seed_default_customers()

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def require_login():
    return "user" in session

def current_user():
    return session.get("user", "")

def error_response(msg, code=400):
    return jsonify({"success": False, "error": msg}), code

def compress_image(path):
    try:
        img = Image.open(path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > 1600:
            ratio = 1600 / float(img.width)
            img = img.resize((1600, int(img.height * ratio)))
        img.save(path, "JPEG", quality=78, optimize=True)
    except Exception as e:
        log_error("compress_image", str(e))

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

@app.route("/api/me")
def api_me():
    if not require_login():
        return jsonify({"success": False, "user": ""})
    return jsonify({"success": True, "user": current_user()})

@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json(silent=True) or request.form or {}
        username = (data.get("username") or data.get("name") or "").strip()
        password = (data.get("password") or "").strip()
        if not username or not password:
            return error_response("帳號密碼不可空白")
        user = get_user(username)
        if not user:
            create_user(username, password)
            log_action(username, "建立帳號")
        else:
            stored = user["password"]
            if stored != password and not str(stored).startswith("pbkdf2:"):
                return error_response("密碼錯誤")
            if str(stored).startswith("pbkdf2:"):
                from werkzeug.security import check_password_hash
                if not check_password_hash(stored, password):
                    return error_response("密碼錯誤")
            elif stored != password:
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
    user = current_user()
    session.clear()
    if user:
        log_action(user, "登出系統")
    return jsonify({"success": True})

@app.route("/api/change_password", methods=["POST"])
def change_password():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        data = request.get_json(force=True)
        old_password = (data.get("old_password") or "").strip()
        new_password = (data.get("new_password") or "").strip()
        if not old_password or not new_password:
            return error_response("密碼不可空白")
        user = get_user(current_user())
        if not user:
            return error_response("帳號不存在", 404)
        stored = user["password"]
        if str(stored).startswith("pbkdf2:"):
            from werkzeug.security import check_password_hash
            ok = check_password_hash(stored, old_password)
        else:
            ok = stored == old_password
        if not ok:
            return error_response("舊密碼錯誤")
        update_user_password(current_user(), new_password)
        log_action(current_user(), "修改密碼")
        return jsonify({"success": True})
    except Exception as e:
        log_error("change_password", str(e))
        return error_response("修改失敗", 500)

@app.route("/api/upload_ocr", methods=["POST"])
def upload_ocr():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        file = request.files.get("file")
        if not file:
            return error_response("未選擇圖片")
        if not allowed_file(file.filename):
            return error_response("圖片格式錯誤")
        content = file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            return error_response("圖片過大")
        image_hash = hashlib.md5(content).hexdigest()
        if image_hash_exists(image_hash):
            return error_response("此圖片已上傳過")
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{image_hash}.{ext}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        with open(path, "wb") as f:
            f.write(content)
        compress_image(path)
        result = process_ocr_text(path)
        save_image_hash(image_hash)
        confidence = result.get("confidence", 0)
        log_action(current_user(), "OCR辨識")
        return jsonify({
            "success": True,
            "text": result.get("text", ""),
            "items": result.get("items", []),
            "confidence": confidence,
            "warning": "辨識信心偏低，請確認內容" if confidence < 80 else "",
            "sync_time": int(os.path.getmtime(path))
        })
    except Exception as e:
        log_error("upload_ocr", str(e))
        return error_response("OCR辨識失敗", 500)

@app.route("/api/save_correction", methods=["POST"])
def api_save_correction():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        data = request.get_json(force=True)
        wrong = (data.get("wrong_text") or "").strip()
        correct = (data.get("correct_text") or "").strip()
        if wrong and correct and wrong != correct:
            save_correction(wrong, correct)
            log_action(current_user(), f"修正OCR {wrong}->{correct}")
        return jsonify({"success": True})
    except Exception as e:
        log_error("save_correction", str(e))
        return error_response("儲存失敗", 500)

@app.route("/api/inventory", methods=["POST"])
def api_inventory():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        data = request.get_json(force=True)
        items = data.get("items", [])
        location = (data.get("location") or "").strip()
        for item in items:
            item["operator"] = current_user()
            if location and not item.get("location"):
                item["location"] = location
            save_inventory(item)
        log_action(current_user(), "建立庫存")
        return jsonify({"success": True, "items": items})
    except Exception as e:
        log_error("inventory", str(e))
        return error_response("建立失敗", 500)

@app.route("/api/order", methods=["POST"])
def api_order():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        data = request.get_json(force=True)
        customer = (data.get("customer") or "").strip()
        items = data.get("items", [])
        save_order(customer, items, current_user())
        log_action(current_user(), f"建立訂單 {customer}")
        return jsonify({"success": True, "customer": customer, "status": "pending"})
    except Exception as e:
        log_error("order", str(e))
        return error_response("訂單建立失敗", 500)

@app.route("/api/master_order", methods=["POST"])
def api_master():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        data = request.get_json(force=True)
        customer = (data.get("customer") or "").strip()
        items = data.get("items", [])
        save_master_order(customer, items, current_user())
        log_action(current_user(), f"更新總單 {customer}")
        return jsonify({"success": True, "customer": customer})
    except Exception as e:
        log_error("master_order", str(e))
        return error_response("總單失敗", 500)

@app.route("/api/ship", methods=["POST"])
def api_ship():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        data = request.get_json(force=True)
        customer = (data.get("customer") or "").strip()
        items = data.get("items", [])
        result = ship_order(customer, items, current_user())
        if result.get("success"):
            log_action(current_user(), f"完成出貨 {customer}")
        return jsonify(result)
    except Exception as e:
        log_error("ship", str(e))
        return error_response("出貨失敗", 500)

@app.route("/api/shipping_records")
def api_shipping():
    try:
        return jsonify({"success": True, "records": get_shipping_records()})
    except Exception as e:
        log_error("shipping_records", str(e))
        return error_response("查詢失敗", 500)

@app.route("/api/find_locations", methods=["POST"])
def api_find_locations():
    try:
        data = request.get_json(force=True)
        return jsonify({"success": True, "items": find_multiple_locations(data.get("items", []))})
    except Exception as e:
        log_error("find_locations", str(e))
        return error_response("定位失敗", 500)

@app.route("/api/customers", methods=["GET", "POST"])
def api_customers():
    try:
        if request.method == "GET":
            return jsonify({"success": True, "customers": list_customers()})
        if not require_login():
            return error_response("請先登入", 401)
        data = request.get_json(force=True)
        customer = save_customer({
            "name": (data.get("name") or "").strip(),
            "phone": (data.get("phone") or "").strip(),
            "address": (data.get("address") or "").strip(),
            "notes": (data.get("notes") or "").strip(),
            "region": (data.get("region") or "北區").strip(),
            "sort_order": int(data.get("sort_order") or 0)
        })
        log_action(current_user(), f"更新客戶資料 {customer['name']}")
        return jsonify({"success": True, "customer": customer})
    except Exception as e:
        log_error("customers", str(e))
        return error_response("客戶資料儲存失敗", 500)

@app.route("/api/customers/<name>", methods=["GET"])
def api_customer_detail(name):
    try:
        customer = get_customer(name)
        if not customer:
            return jsonify({"success": False, "customer": None}), 404
        return jsonify({"success": True, "customer": customer})
    except Exception as e:
        log_error("customer_detail", str(e))
        return error_response("查詢失敗", 500)

@app.route("/api/warehouse_slots", methods=["GET", "POST"])
def api_warehouse_slots():
    try:
        if request.method == "GET":
            return jsonify({"success": True, "slots": list_warehouse_slots()})
        if not require_login():
            return error_response("請先登入", 401)
        data = request.get_json(force=True)
        slot = save_warehouse_slot({
            "slot_name": (data.get("slot_name") or "").strip(),
            "customer": (data.get("customer") or "").strip(),
            "product": (data.get("product") or "").strip(),
            "quantity": int(data.get("quantity") or 0),
            "note": (data.get("note") or "").strip()
        })
        log_action(current_user(), f"更新倉庫格位 {slot['slot_name']}")
        return jsonify({"success": True, "slot": slot})
    except Exception as e:
        log_error("warehouse_slots", str(e))
        return error_response("倉庫格位儲存失敗", 500)

@app.route("/api/warehouse_slots/<slot_name>", methods=["DELETE"])
def api_delete_warehouse_slot(slot_name):
    try:
        if not require_login():
            return error_response("請先登入", 401)
        delete_warehouse_slot(slot_name)
        log_action(current_user(), f"刪除倉庫格位 {slot_name}")
        return jsonify({"success": True})
    except Exception as e:
        log_error("delete_warehouse_slot", str(e))
        return error_response("刪除失敗", 500)

@app.route("/api/settings")
def api_settings():
    try:
        return jsonify({"success": True, "settings": get_settings()})
    except Exception as e:
        log_error("settings", str(e))
        return error_response("查詢失敗", 500)

@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    try:
        if not require_login():
            return error_response("請先登入", 401)
        data = request.get_json(force=True)
        key = (data.get("key") or "").strip()
        value = (data.get("value") or "").strip()
        if not key:
            return error_response("KEY 不可空白")
        set_setting(key, value)
        log_action(current_user(), f"更新設定 {key}")
        return jsonify({"success": True})
    except Exception as e:
        log_error("save_settings", str(e))
        return error_response("儲存失敗", 500)

@app.route("/api/backup")
def api_backup():
    return jsonify(run_daily_backup())

@app.route("/api/backups")
def api_backups():
    return jsonify(list_backups())

@app.route("/health")
def health():
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
