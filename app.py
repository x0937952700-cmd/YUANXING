
import hashlib
import os
from functools import wraps
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory

from db import (
    init_db, get_user, create_user, update_user_password, log_action, log_error,
    save_order, save_master_order, ship_order, list_orders, list_master_orders,
    list_shipping_records, upsert_inventory, list_inventory, inventory_summary,
    save_correction, save_image_hash, image_hash_exists, list_logs, list_errors,
    latest_notifications, save_notification, mark_notifications_read,
    unread_notification_count, list_notifications, dashboard_summary,
    list_customers, update_customer, search_customers, sync_customer,
    save_warehouse_cell, warehouse_grid, reconcile_data, list_settings,
    save_setting, get_setting, list_warehouse_cells, list_settings, list_inventory,
)
from ocr import process_ocr_text
from backup import run_daily_backup, list_backups

from PIL import Image

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "yuanxing-secret-key")
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_UPLOAD_SIZE = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE

init_db()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def require_login():
    return "user" in session


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not require_login():
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "請先登入"}), 401
            return redirect(url_for("login_page"))
        return fn(*args, **kwargs)
    return wrapper


def error_response(msg, status=400):
    return jsonify({"success": False, "error": msg}), status


def safe_json():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict() or {}


def compress_image(path):
    try:
        img = Image.open(path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > 1800:
            ratio = 1800 / float(img.width)
            img = img.resize((1800, int(img.height * ratio)))
        img.save(path, "JPEG", quality=80, optimize=True)
    except Exception as e:
        log_error("compress_image", str(e))


def current_user():
    return session.get("user", "")


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "API not found"}), 404
    return render_template("login.html", error="找不到頁面"), 404


@app.errorhandler(413)
def too_large(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "圖片過大"}), 413
    return render_template("login.html", error="圖片過大"), 413


@app.errorhandler(500)
def server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "伺服器錯誤"}), 500
    return render_template("login.html", error="伺服器錯誤"), 500


@app.route("/favicon.ico")
def favicon():
    return send_from_directory("static/icons", "icon-192.png")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json", mimetype="application/manifest+json")


@app.route("/service-worker.js")
def service_worker():
    return send_from_directory(".", "service-worker.js", mimetype="application/javascript")


@app.route("/")
def home():
    if not require_login():
        return redirect(url_for("login_page"))
    summary = dashboard_summary()
    return render_template(
        "index.html",
        user=current_user(),
        summary=summary,
        unread_count=summary["unread_notifications"],
        title="沅興木業",
    )


@app.route("/login")
def login_page():
    if require_login():
        return redirect(url_for("home"))
    return render_template("login.html", error="")


@app.route("/logout", methods=["POST"])
@login_required
def logout_page():
    user = current_user()
    session.clear()
    if user:
        log_action(user, "登出系統")
    return redirect(url_for("login_page"))


@app.route("/module/<module_name>")
@login_required
def module_page(module_name):
    module_name = module_name.lower()
    allowed = {
        "inventory", "orders", "master_orders", "shipping", "shipping_records",
        "warehouse", "customers", "today", "settings", "reconcile"
    }
    if module_name not in allowed:
        return render_template("login.html", error="找不到模組"), 404

    summary = dashboard_summary()
    module_data = {
        "inventory": inventory_summary(),
        "orders": list_orders(),
        "master_orders": list_master_orders(),
        "shipping_records": list_shipping_records(),
        "customers": list_customers(),
        "warehouse_a": warehouse_grid("A"),
        "warehouse_b": warehouse_grid("B"),
        "notifications": list_notifications(100),
        "logs": list_logs(200),
        "errors": list_errors(50),
        "backups": list_backups().get("files", []),
        "discrepancies": reconcile_data(),
        "summary": summary,
        "settings": list_settings(),
    }
    return render_template(
        "module.html",
        user=current_user(),
        module=module_name,
        data=module_data,
        unread_count=summary["unread_notifications"],
        title="沅興木業",
    )


@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        data = safe_json()
        username = (data.get("username") or data.get("name") or "").strip()
        password = (data.get("password") or "").strip()
        remember = str(data.get("remember", "1")).lower() not in {"0", "false", "no"}

        if not username or not password:
            return error_response("帳號密碼不可空白")

        user = get_user(username)
        if not user:
            create_user(username, password)
            log_action(username, "建立帳號")
        elif user["password"] != password:
            return error_response("密碼錯誤")

        session.permanent = remember
        session["user"] = username
        log_action(username, "登入系統")
        return jsonify({"success": True, "username": username})
    except Exception as e:
        log_error("api_login", str(e))
        return error_response("登入失敗", 500)


@app.route("/api/logout", methods=["POST"])
def api_logout():
    user = current_user()
    session.clear()
    if user:
        log_action(user, "登出系統")
    return jsonify({"success": True})


@app.route("/api/change_password", methods=["POST"])
@login_required
def api_change_password():
    try:
        data = safe_json()
        old_password = (data.get("old_password") or "").strip()
        new_password = (data.get("new_password") or "").strip()
        confirm_password = (data.get("confirm_password") or "").strip()
        user = get_user(current_user())
        if not user or user["password"] != old_password:
            return error_response("舊密碼錯誤")
        if not new_password or new_password != confirm_password:
            return error_response("新密碼與確認密碼不一致")
        update_user_password(current_user(), new_password)
        log_action(current_user(), "修改密碼")
        return jsonify({"success": True})
    except Exception as e:
        log_error("change_password", str(e))
        return error_response("修改密碼失敗", 500)


@app.route("/api/upload_ocr", methods=["POST"])
@login_required
def api_upload_ocr():
    try:
        if "file" not in request.files:
            return error_response("未選擇圖片")
        file = request.files["file"]
        if not file or not allowed_file(file.filename):
            return error_response("格式錯誤")

        content = file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            return error_response("圖片過大", 413)

        image_hash = hashlib.md5(content).hexdigest()
        ext = file.filename.rsplit(".", 1)[1].lower()
        filename = f"{image_hash}.{ext}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        with open(path, "wb") as f:
            f.write(content)

        compress_image(path)

        region = request.form.get("region", "")
        region_vals = None
        if region:
            try:
                region_vals = [int(v) for v in region.split(",")]
            except Exception:
                region_vals = None

        blue_only = str(request.form.get("blue_only", "1")).lower() not in {"0", "false", "no"}
        result = process_ocr_text(path, region=region_vals, blue_only=blue_only)
        ocr_text = result.get("text", "")

        # duplicate files should still show text, not block
        existing = image_hash_exists(image_hash)
        if existing:
            save_image_hash(image_hash, path, ocr_text or existing.get("ocr_text", ""))
        else:
            save_image_hash(image_hash, path, ocr_text)

        log_action(current_user(), "OCR辨識", target_type="image", target_name=filename, detail=result.get("text", ""))
        save_notification(
            title=f"{current_user()}｜OCR辨識完成",
            message="已完成圖片辨識",
            category="ocr",
            actor=current_user(),
            target_type="image",
            target_name=filename,
        )

        return jsonify({
            "success": True,
            "text": ocr_text,
            "items": result.get("items", []),
            "confidence": result.get("confidence", 0),
            "warning": result.get("warning", ""),
            "customer_guess": result.get("customer_guess", ""),
            "duplicate": bool(existing),
            "sync_time": int(os.path.getmtime(path)),
        })
    except Exception as e:
        log_error("upload_ocr", str(e))
        return error_response("OCR辨識失敗", 500)


@app.route("/api/save_correction", methods=["POST"])
@login_required
def api_save_correction():
    try:
        data = safe_json()
        wrong = (data.get("wrong_text") or "").strip()
        correct = (data.get("correct_text") or "").strip()
        save_correction(wrong, correct)
        if wrong and correct and wrong != correct:
            log_action(current_user(), f"修正OCR {wrong}->{correct}", target_type="ocr")
        return jsonify({"success": True})
    except Exception as e:
        log_error("save_correction", str(e))
        return error_response("儲存失敗", 500)


@app.route("/api/inventory", methods=["GET", "POST"])
@login_required
def api_inventory():
    try:
        if request.method == "GET":
            return jsonify({"success": True, "items": inventory_summary(), "raw": list_inventory()})
        data = safe_json()
        items = data.get("items", [])
        operator = current_user()
        for item in items:
            upsert_inventory(
                product=item.get("product") or item.get("product_name") or "",
                quantity=int(item.get("quantity") or 0),
                location=item.get("location", ""),
                customer_name=item.get("customer_name", ""),
                operator=operator,
                warehouse_zone=item.get("warehouse_zone", ""),
                band_no=int(item.get("band_no") or 0),
                row_label=item.get("row_label", ""),
                cell_no=int(item.get("cell_no") or 0),
            )
        log_action(operator, "建立庫存", target_type="inventory", detail=str(items))
        save_notification(f"{operator}｜更新了庫存", "庫存已更新", "inventory", operator, "inventory", "")
        return jsonify({"success": True})
    except Exception as e:
        log_error("inventory", str(e))
        return error_response("建立失敗", 500)


@app.route("/api/orders", methods=["GET", "POST"])
@login_required
def api_orders():
    try:
        if request.method == "GET":
            return jsonify({"success": True, "items": list_orders()})
        data = safe_json()
        customer = (data.get("customer") or "").strip()
        items = data.get("items", [])
        note = data.get("note", "")
        save_order(customer, items, current_user(), note=note)
        log_action(current_user(), "建立訂單", target_type="order", target_name=customer, detail=str(items))
        save_notification(f"{current_user()}｜建立訂單", f"{customer} 訂單已建立", "order", current_user(), "customer", customer)
        return jsonify({"success": True})
    except Exception as e:
        log_error("orders", str(e))
        return error_response("訂單建立失敗", 500)


@app.route("/api/master_orders", methods=["GET", "POST"])
@login_required
def api_master_orders():
    try:
        if request.method == "GET":
            return jsonify({"success": True, "items": list_master_orders()})
        data = safe_json()
        customer = (data.get("customer") or "").strip()
        items = data.get("items", [])
        note = data.get("note", "")
        save_master_order(customer, items, current_user(), note=note)
        log_action(current_user(), "更新總單", target_type="master_order", detail=str(items))
        save_notification(f"{current_user()}｜更新總單", "總單已更新", "master", current_user(), "customer", customer)
        return jsonify({"success": True})
    except Exception as e:
        log_error("master_orders", str(e))
        return error_response("總單失敗", 500)


@app.route("/api/ship", methods=["POST"])
@login_required
def api_ship():
    try:
        data = safe_json()
        customer = (data.get("customer") or "").strip()
        items = data.get("items", [])
        result = ship_order(customer, items, current_user())
        if result.get("success"):
            log_action(current_user(), "完成出貨", target_type="shipping", target_name=customer, detail=str(items))
            save_notification(f"{current_user()}｜已完成出貨", f"{customer} 已出貨", "shipping", current_user(), "customer", customer)
            return jsonify(result)
        return error_response(result.get("error", "出貨失敗"), 400)
    except Exception as e:
        log_error("ship", str(e))
        return error_response("出貨失敗", 500)


@app.route("/api/shipping_records", methods=["GET"])
@login_required
def api_shipping_records():
    try:
        days = request.args.get("days", "").strip()
        records = list_shipping_records()
        if days:
            try:
                days_int = int(days)
                cutoff = datetime.now() - timedelta(days=days_int)
                cutoff_str = cutoff.strftime("%Y-%m-%d")
                records = [r for r in records if r["shipped_at"] >= cutoff_str]
            except Exception:
                pass
        return jsonify({"success": True, "records": records})
    except Exception as e:
        log_error("shipping_records", str(e))
        return error_response("查詢失敗", 500)


@app.route("/api/customers", methods=["GET"])
@login_required
def api_customers():
    try:
        q = request.args.get("q", "").strip()
        items = list_customers()
        if q:
            items = [x for x in items if q in x["customer_name"]]
        return jsonify({"success": True, "items": items})
    except Exception as e:
        log_error("customers", str(e))
        return error_response("查詢失敗", 500)


@app.route("/api/customers/search", methods=["GET"])
@login_required
def api_customers_search():
    try:
        q = request.args.get("q", "").strip()
        return jsonify({"success": True, "items": search_customers(q)})
    except Exception as e:
        log_error("customers_search", str(e))
        return error_response("查詢失敗", 500)


@app.route("/api/customers/update", methods=["POST"])
@login_required
def api_customers_update():
    try:
        data = safe_json()
        customer_name = (data.get("customer_name") or "").strip()
        update_customer(
            customer_name,
            phone=data.get("phone", ""),
            address=data.get("address", ""),
            special_requests=data.get("special_requests", ""),
            region=data.get("region", ""),
        )
        log_action(current_user(), "修改客戶資料", target_type="customer", target_name=customer_name, detail=str(data))
        save_notification(f"{current_user()}｜修改客戶資料", customer_name, "customer", current_user(), "customer", customer_name)
        return jsonify({"success": True})
    except Exception as e:
        log_error("customers_update", str(e))
        return error_response("更新失敗", 500)


@app.route("/api/warehouse", methods=["GET", "POST"])
@login_required
def api_warehouse():
    try:
        if request.method == "GET":
            zone = request.args.get("zone", "A").upper()
            return jsonify({"success": True, "zone": zone, "bands": warehouse_grid(zone), "cells": list_warehouse_cells(zone)})
        data = safe_json()
        save_warehouse_cell(
            zone=(data.get("zone") or "A").upper(),
            band_no=int(data.get("band_no") or 1),
            row_label=(data.get("row_label") or "front"),
            cell_no=int(data.get("cell_no") or 1),
            customer_name=data.get("customer_name", ""),
            product=data.get("product", ""),
            quantity=int(data.get("quantity") or 0),
            note=data.get("note", ""),
        )
        log_action(current_user(), "更新倉庫格位", target_type="warehouse", detail=str(data))
        save_notification(f"{current_user()}｜更新倉庫圖", "倉庫格位已更新", "warehouse", current_user(), "warehouse", "")
        return jsonify({"success": True})
    except Exception as e:
        log_error("warehouse", str(e))
        return error_response("倉庫圖更新失敗", 500)


@app.route("/api/warehouse/slots", methods=["GET"])
@login_required
def api_warehouse_slots():
    try:
        zone = request.args.get("zone", "A").upper()
        band_no = int(request.args.get("band_no") or 1)
        row_label = request.args.get("row_label", "front")
        cell_no = int(request.args.get("cell_no") or 1)
        slot_key = f"{zone}-{band_no}-{row_label}-{cell_no}"
        cells = list_warehouse_cells(zone)
        found = next((x for x in cells if x["slot_key"] == slot_key), None)
        suggestions = []
        for row in list_inventory():
            suggestions.append({
                "customer_name": row.get("customers", [""])[0] if row.get("customers") else "",
                "product": row["product"],
                "quantity": row["quantity"],
                "slot_key": row.get("locations", [""])[0] if row.get("locations") else "",
            })
        return jsonify({
            "success": True,
            "cell": found,
            "suggestions": suggestions,
            "search_index": [s["product"] for s in suggestions] + [s["customer_name"] for s in suggestions if s.get("customer_name")],
        })
    except Exception as e:
        log_error("warehouse_slots", str(e))
        return error_response("查詢格位失敗", 500)


@app.route("/api/reconcile", methods=["GET"])
@login_required
def api_reconcile():
    try:
        return jsonify({"success": True, "items": reconcile_data()})
    except Exception as e:
        log_error("reconcile", str(e))
        return error_response("對帳失敗", 500)


@app.route("/api/summary", methods=["GET"])
@login_required
def api_summary():
    try:
        return jsonify({"success": True, "summary": dashboard_summary()})
    except Exception as e:
        log_error("summary", str(e))
        return error_response("統計失敗", 500)


@app.route("/api/notifications", methods=["GET"])
@login_required
def api_get_notifications():
    try:
        unread_only = request.args.get("unread_only", "0") in {"1", "true", "yes"}
        return jsonify({"success": True, "items": list_notifications(100, unread_only=unread_only), "unread_count": unread_notification_count()})
    except Exception as e:
        log_error("notifications", str(e))
        return error_response("查詢失敗", 500)


@app.route("/api/notifications/latest", methods=["GET"])
@login_required
def api_latest_notifications():
    try:
        since_id = int(request.args.get("since_id", 0) or 0)
        return jsonify({"success": True, "items": latest_notifications(since_id, 50), "unread_count": unread_notification_count()})
    except Exception as e:
        log_error("notifications_latest", str(e))
        return error_response("查詢失敗", 500)


@app.route("/api/notifications/read", methods=["POST"])
@login_required
def api_notifications_read():
    try:
        data = safe_json()
        ids = data.get("ids", [])
        if ids:
            mark_notifications_read(ids)
        else:
            mark_notifications_read()
        return jsonify({"success": True})
    except Exception as e:
        log_error("notifications_read", str(e))
        return error_response("更新失敗", 500)


@app.route("/api/today_changes", methods=["GET"])
@login_required
def api_today_changes():
    try:
        summary = dashboard_summary()
        return jsonify({
            "success": True,
            "summary": summary,
            "notifications": summary["today_notifications"],
            "logs": summary["today_logs"],
            "unplaced_items": summary["unplaced_items"],
            "discrepancies": reconcile_data(),
        })
    except Exception as e:
        log_error("today_changes", str(e))
        return error_response("查詢失敗", 500)


@app.route("/api/audit", methods=["GET"])
@login_required
def api_audit():
    try:
        return jsonify({"success": True, "items": list_logs(300)})
    except Exception as e:
        log_error("audit", str(e))
        return error_response("查詢失敗", 500)


@app.route("/api/backup", methods=["POST", "GET"])
@login_required
def api_backup():
    try:
        result = run_daily_backup()
        log_action(current_user(), "手動備份", target_type="backup", detail=str(result))
        return jsonify(result)
    except Exception as e:
        log_error("backup", str(e))
        return error_response("備份失敗", 500)


@app.route("/api/backups", methods=["GET"])
@login_required
def api_backups():
    try:
        return jsonify(list_backups())
    except Exception as e:
        log_error("backups", str(e))
        return error_response("查詢失敗", 500)


@app.route("/api/settings", methods=["GET", "POST"])
@login_required
def api_settings():
    try:
        if request.method == "GET":
            return jsonify({"success": True, "items": list_settings()})
        data = safe_json()
        for key, value in data.items():
            save_setting(key, str(value))
        log_action(current_user(), "更新設定", target_type="settings", detail=str(data))
        return jsonify({"success": True})
    except Exception as e:
        log_error("settings", str(e))
        return error_response("更新失敗", 500)


@app.route("/health")
def health():
    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
