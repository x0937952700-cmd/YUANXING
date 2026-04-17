from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import timedelta
import os
import hashlib
import json
from PIL import Image

from db import (
    init_db, now, today_str,
    get_user, create_user, update_user_password,
    log_action, add_notification, list_notifications, mark_notifications_read,
    list_inventory, upsert_inventory,
    save_order, list_orders, save_master_order, list_master_orders,
    list_shipping_records, list_customers, update_customer, upsert_customer, suggest_customers,
    save_warehouse_cell, delete_warehouse_cell, list_warehouse_cells, warehouse_search,
    get_unplaced_products, dashboard_summary, reconciliation,
    execute, query_all, query_one, save_correction
)
from ocr import process_ocr_text
from backup import run_daily_backup, list_backups

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "yuanxing-secret")
app.permanent_session_lifetime = timedelta(days=30)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


# ---------- init ----------
init_db()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def require_login():
    return "user" in session


def error_response(msg, status=400):
    return jsonify({"success": False, "error": msg}), status


def compress_image(path):
    try:
        img = Image.open(path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > 1800:
            ratio = 1800 / float(img.width)
            img = img.resize((1800, int(img.height * ratio)))
        img.save(path, "JPEG", quality=80, optimize=True)
    except Exception:
        pass


def save_image_hash(image_hash):
    row = query_one("SELECT id FROM image_hashes WHERE image_hash=?", (image_hash,))
    if not row:
        execute("INSERT INTO image_hashes(image_hash, created_at) VALUES(?,?)", (image_hash, now()))


def image_hash_exists(image_hash):
    return query_one("SELECT id FROM image_hashes WHERE image_hash=?", (image_hash,)) is not None


def json_request():
    try:
        return request.get_json(force=True) or {}
    except Exception:
        return {}


def redirect_login():
    return redirect(url_for("login_page"))


# ---------- pages ----------
@app.route("/")
def home():
    if not require_login():
        return redirect_login()
    summary = dashboard_summary()
    return render_template(
        "index.html",
        user=session.get("user"),
        summary=summary,
        unread_notifications=summary.get("unread_notifications", 0),
        title="沅興木業"
    )


@app.route("/login")
def login_page():
    if require_login():
        return redirect(url_for("home"))
    return render_template("login.html", title="沅興木業登入")


@app.route("/module/<module_name>")
def module_page(module_name):
    if not require_login():
        return redirect_login()
    allowed = {"inventory", "orders", "master_orders", "shipping", "shipping_records", "warehouse", "customers", "today_changes"}
    if module_name not in allowed:
        return redirect(url_for("home"))
    return render_template("module.html", module=module_name, user=session.get("user"), title="沅興木業")


# ---------- auth ----------
@app.route("/api/login", methods=["POST"])
def api_login():
    data = json_request()
    username = (data.get("username") or data.get("name") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or not password:
        return error_response("帳號密碼不可空白")
    user = get_user(username)
    if not user:
        create_user(username, password)
        log_action(username, "建立帳號", "user", username)
    elif user["password"] != password:
        return error_response("密碼錯誤")
    session.permanent = True
    session["user"] = username
    log_action(username, "登入系統", "auth", username)
    return jsonify({"success": True, "username": username, "redirect": url_for("home")})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    username = session.get("user", "")
    if username:
        log_action(username, "登出系統", "auth", username)
    session.clear()
    return jsonify({"success": True})


@app.route("/api/change_password", methods=["POST"])
def api_change_password():
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    old = (data.get("old_password") or "").strip()
    new = (data.get("new_password") or "").strip()
    user = get_user(session["user"])
    if not user or user["password"] != old:
        return error_response("舊密碼錯誤")
    if len(new) < 4:
        return error_response("新密碼至少 4 碼")
    update_user_password(session["user"], new)
    log_action(session["user"], "修改密碼", "auth", session["user"])
    return jsonify({"success": True})


# ---------- dashboard ----------
@app.route("/api/dashboard")
def api_dashboard():
    if not require_login():
        return error_response("請先登入", 401)
    return jsonify({"success": True, "summary": dashboard_summary(), "reconciliation": reconciliation(), "today": today_str()})


@app.route("/api/today_changes")
def api_today_changes():
    if not require_login():
        return error_response("請先登入", 401)
    today = today_str()
    logs = query_all("SELECT * FROM logs WHERE created_at LIKE ? ORDER BY id DESC", (today + "%",))
    notifications = list_notifications(limit=200)
    if notifications:
        from db import mark_notifications_read
        mark_notifications_read([n["id"] for n in notifications if not int(n.get("read_flag") or 0)])
    summary = dashboard_summary()
    return jsonify({"success": True, "logs": logs, "notifications": notifications, "summary": summary})


# ---------- customers ----------
@app.route("/api/customers")
def api_customers():
    if not require_login():
        return error_response("請先登入", 401)
    return jsonify({"success": True, "customers": list_customers()})


@app.route("/api/customers/suggest")
def api_customers_suggest():
    if not require_login():
        return error_response("請先登入", 401)
    q = request.args.get("q", "")
    return jsonify({"success": True, "customers": suggest_customers(q)})


@app.route("/api/customers/<int:customer_id>", methods=["POST"])
def api_update_customer(customer_id):
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    update_customer(customer_id, **data)
    log_action(session["user"], "修改客戶資料", "customer", str(customer_id), data)
    add_notification("customer", f"{session['user']}｜更新了客戶資料", session["user"], data)
    return jsonify({"success": True})


# ---------- inventory ----------
@app.route("/api/inventory")
def api_inventory():
    if not require_login():
        return error_response("請先登入", 401)
    return jsonify({"success": True, "items": list_inventory(), "unplaced": [r["product"] for r in get_unplaced_products()]})


@app.route("/api/inventory/save", methods=["POST"])
def api_inventory_save():
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    items = data.get("items") or []
    results = []
    for item in items:
        product = item.get("product") or item.get("product_name") or ""
        qty = int(item.get("quantity") or 1)
        location = item.get("location") or ""
        customer_name = item.get("customer_name") or ""
        note = item.get("note") or ""
        upsert_customer(customer_name) if customer_name else None
        upsert_inventory(product, qty, location, customer_name, session["user"], note)
        log_action(session["user"], "建立庫存", "inventory", product, item)
        add_notification("inventory", f"{session['user']}｜更新了庫存", session["user"], item)
        results.append({"product": product, "qty": qty})
    return jsonify({"success": True, "items": results})


# ---------- OCR ----------
@app.route("/api/upload_ocr", methods=["POST"])
def api_upload_ocr():
    if not require_login():
        return error_response("請先登入", 401)
    file = request.files.get("file")
    if not file:
        return error_response("未選擇圖片")
    if not allowed_file(file.filename):
        return error_response("圖片格式錯誤")
    content = file.read()
    if len(content) > app.config["MAX_CONTENT_LENGTH"]:
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

    # optional region crop coords
    region = None
    try:
        x = request.form.get("crop_x")
        y = request.form.get("crop_y")
        w = request.form.get("crop_w")
        h = request.form.get("crop_h")
        if all(v not in (None, "", "undefined") for v in [x, y, w, h]):
            region = [int(x), int(y), int(w), int(h)]
    except Exception:
        region = None

    customer_keyword = request.form.get("customer_keyword", "")
    result = process_ocr_text(path, region=region, customer_keyword=customer_keyword)
    save_image_hash(image_hash)

    # store correction if manual correction supplied
    manual_text = request.form.get("manual_text", "").strip()
    if manual_text:
        for line in manual_text.splitlines():
            if line.strip():
                save_correction(line.strip(), line.strip())

    log_action(session["user"], "OCR辨識", "ocr", file.filename, {"confidence": result.get("confidence", 0)})
    if result.get("warning"):
        add_notification("ocr", f"{session['user']}｜OCR 信心偏低", session["user"], result)

    return jsonify({
        "success": True,
        "text": result.get("text", ""),
        "items": result.get("items", []),
        "confidence": result.get("confidence", 0),
        "warning": result.get("warning", ""),
        "customer_name": result.get("customer_name", ""),
        "sync_time": int(os.path.getmtime(path))
    })


@app.route("/api/save_correction", methods=["POST"])
def api_save_correction():
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    wrong = (data.get("wrong_text") or "").strip()
    correct = (data.get("correct_text") or "").strip()
    if wrong and correct and wrong != correct:
        save_correction(wrong, correct)
        log_action(session["user"], f"修正OCR {wrong}->{correct}", "ocr", wrong)
        add_notification("ocr", f"{session['user']}｜已修正 OCR", session["user"], {"wrong": wrong, "correct": correct})
    return jsonify({"success": True})


# ---------- orders / master / shipping ----------
def parse_items(items):
    normalized = []
    for item in items or []:
        product = item.get("product") or item.get("product_name") or ""
        qty = int(item.get("quantity") or 1)
        if product:
            normalized.append({"product": product, "quantity": qty})
    return normalized


@app.route("/api/orders")
def api_orders():
    if not require_login():
        return error_response("請先登入", 401)
    return jsonify({"success": True, "items": list_orders()})


@app.route("/api/orders/save", methods=["POST"])
def api_orders_save():
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    customer = (data.get("customer_name") or data.get("customer") or "").strip()
    items = parse_items(data.get("items"))
    created = save_order(customer, items, session["user"])
    log_action(session["user"], "建立訂單", "order", customer, {"items": created})
    add_notification("order", f"{session['user']}｜新增訂單", session["user"], {"customer": customer})
    return jsonify({"success": True, "items": created})


@app.route("/api/master_orders")
def api_master_orders():
    if not require_login():
        return error_response("請先登入", 401)
    return jsonify({"success": True, "items": list_master_orders()})


@app.route("/api/master_orders/save", methods=["POST"])
def api_master_orders_save():
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    customer = (data.get("customer_name") or data.get("customer") or "").strip()
    items = parse_items(data.get("items"))
    save_master_order(customer, items, session["user"])
    log_action(session["user"], "更新總單", "master_order", customer, {"items": items})
    add_notification("master_order", f"{session['user']}｜更新總單", session["user"], {"customer": customer})
    return jsonify({"success": True})


def deduct_orders(customer, product, qty):
    """
    Reduce master_orders first then orders; returns deducted counts.
    """
    remaining = int(qty)
    master_deduct = 0
    order_deduct = 0

    # master orders
    rows = query_all("SELECT id, qty FROM master_orders WHERE customer_name=? AND product=? ORDER BY id ASC", (customer, product))
    for row in rows:
        if remaining <= 0:
            break
        take = min(int(row["qty"]), remaining)
        if take > 0:
            new_qty = int(row["qty"]) - take
            execute("UPDATE master_orders SET qty=?, updated_at=? WHERE id=?", (new_qty, now(), row["id"]))
            master_deduct += take
            remaining -= take

    # orders
    rows = query_all("SELECT id, qty FROM orders WHERE customer_name=? AND product=? AND status!='shipped' ORDER BY id ASC", (customer, product))
    for row in rows:
        if remaining <= 0:
            break
        take = min(int(row["qty"]), remaining)
        if take > 0:
            new_qty = int(row["qty"]) - take
            if new_qty <= 0:
                execute("UPDATE orders SET qty=0, status='shipped', updated_at=? WHERE id=?", (now(), row["id"]))
            else:
                execute("UPDATE orders SET qty=?, status='partial', updated_at=? WHERE id=?", (new_qty, now(), row["id"]))
            order_deduct += take
            remaining -= take

    return master_deduct, order_deduct, remaining


def deduct_inventory(product, qty):
    remaining = int(qty)
    inventory_deduct = 0
    rows = query_all("SELECT id, quantity FROM inventory WHERE product=? AND quantity>0 ORDER BY quantity DESC", (product,))
    total = sum(int(r["quantity"]) for r in rows)
    if total < qty:
        return None, f"{product} 庫存不足"
    for row in rows:
        if remaining <= 0:
            break
        take = min(int(row["quantity"]), remaining)
        execute("UPDATE inventory SET quantity = quantity - ?, updated_at=? WHERE id=?", (take, now(), row["id"]))
        remaining -= take
        inventory_deduct += take
    return inventory_deduct, None




@app.route("/api/ship", methods=["POST"])
def api_ship():
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    customer = (data.get("customer_name") or data.get("customer") or "").strip()
    items = parse_items(data.get("items"))
    if not customer or not items:
        return error_response("資料不足")

    from db import get_db, sql as dbsql
    with get_db() as conn:
        try:
            cur = conn.cursor()
            details = []
            total_master = 0
            total_order = 0
            total_inventory = 0

            for item in items:
                product = item["product"]
                qty = int(item["quantity"])

                cur.execute(dbsql("SELECT COALESCE(SUM(qty), 0) FROM master_orders WHERE customer_name=? AND product=?"), (customer, product))
                master_total = int(cur.fetchone()[0])

                cur.execute(dbsql("SELECT COALESCE(SUM(qty), 0) FROM orders WHERE customer_name=? AND product=? AND status!='shipped'"), (customer, product))
                order_total = int(cur.fetchone()[0])

                cur.execute(dbsql("SELECT COALESCE(SUM(quantity), 0) FROM inventory WHERE product=?"), (product,))
                inventory_total = int(cur.fetchone()[0])

                if inventory_total < qty:
                    conn.rollback()
                    return error_response(f"{product} 庫存不足")

                master_take = min(master_total, qty)
                order_take = min(order_total, max(qty - master_take, 0))
                inventory_take = qty

                # Deduct master orders first
                if master_take > 0:
                    cur.execute(dbsql("SELECT id, qty FROM master_orders WHERE customer_name=? AND product=? AND qty>0 ORDER BY id ASC"), (customer, product))
                    rows = cur.fetchall()
                    remaining = master_take
                    for row in rows:
                        if remaining <= 0:
                            break
                        rid = row[0] if isinstance(row, tuple) else row["id"]
                        rqty = row[1] if isinstance(row, tuple) else row["qty"]
                        take = min(int(rqty), remaining)
                        cur.execute(dbsql("UPDATE master_orders SET qty = qty - ?, updated_at=? WHERE id=?"), (take, now(), rid))
                        remaining -= take

                # Deduct orders next
                if order_take > 0:
                    cur.execute(dbsql("SELECT id, qty FROM orders WHERE customer_name=? AND product=? AND status!='shipped' AND qty>0 ORDER BY id ASC"), (customer, product))
                    rows = cur.fetchall()
                    remaining = order_take
                    for row in rows:
                        if remaining <= 0:
                            break
                        rid = row[0] if isinstance(row, tuple) else row["id"]
                        rqty = row[1] if isinstance(row, tuple) else row["qty"]
                        take = min(int(rqty), remaining)
                        new_qty = int(rqty) - take
                        if new_qty <= 0:
                            cur.execute(dbsql("UPDATE orders SET qty=0, status='shipped', updated_at=? WHERE id=?"), (now(), rid))
                        else:
                            cur.execute(dbsql("UPDATE orders SET qty=?, status='partial', updated_at=? WHERE id=?"), (new_qty, now(), rid))
                        remaining -= take

                # Deduct inventory last
                cur.execute(dbsql("SELECT id, quantity FROM inventory WHERE product=? AND quantity>0 ORDER BY quantity DESC"), (product,))
                rows = cur.fetchall()
                remaining = inventory_take
                inv_deducted = 0
                for row in rows:
                    if remaining <= 0:
                        break
                    rid = row[0] if isinstance(row, tuple) else row["id"]
                    rqty = row[1] if isinstance(row, tuple) else row["quantity"]
                    take = min(int(rqty), remaining)
                    cur.execute(dbsql("UPDATE inventory SET quantity = quantity - ?, updated_at=? WHERE id=?"), (take, now(), rid))
                    remaining -= take
                    inv_deducted += take

                details.append({
                    "product": product,
                    "qty": qty,
                    "master": master_take,
                    "order": order_take,
                    "inventory": inv_deducted
                })
                total_master += master_take
                total_order += order_take
                total_inventory += inv_deducted

            cur.execute(
                dbsql("INSERT INTO shipping_records(customer_name, product, qty, operator, deducted_master, deducted_order, deducted_inventory, details_json, shipped_at) VALUES(?,?,?,?,?,?,?,?,?)"),
                (
                    customer,
                    json.dumps([d["product"] for d in details], ensure_ascii=False),
                    sum(d["qty"] for d in details),
                    session["user"],
                    total_master,
                    total_order,
                    total_inventory,
                    json.dumps(details, ensure_ascii=False),
                    now()
                )
            )
            conn.commit()

            log_action(session["user"], "完成出貨", "shipping", customer, {"details": details})
            add_notification("shipping", f"{session['user']}｜已完成出貨", session["user"], {"customer": customer, "details": details})
            return jsonify({
                "success": True,
                "details": details,
                "message": "出貨完成",
                "customer": customer,
                "deducted_master": total_master,
                "deducted_order": total_order,
                "deducted_inventory": total_inventory
            })
        except Exception as e:
            conn.rollback()
            return error_response("出貨失敗: " + str(e))


# ---------- warehouse ----------
@app.route("/api/warehouse")
def api_warehouse():
    if not require_login():
        return error_response("請先登入", 401)
    zone = request.args.get("zone")
    cells = list_warehouse_cells(zone)
    products = [r["product"] for r in list_inventory()]
    return jsonify({"success": True, "cells": cells, "products": products})


@app.route("/api/warehouse/search")
def api_warehouse_search():
    if not require_login():
        return error_response("請先登入", 401)
    q = request.args.get("q", "")
    return jsonify({"success": True, "cells": warehouse_search(q)})


@app.route("/api/warehouse/save", methods=["POST"])
def api_warehouse_save():
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    zone = data.get("zone", "A")
    column_no = int(data.get("column_no", 1))
    position = data.get("position", "front")
    slot_no = int(data.get("slot_no", 1))
    customer_name = (data.get("customer_name") or "").strip()
    product = (data.get("product") or "").strip()
    qty = int(data.get("qty") or 0)
    note = (data.get("note") or "").strip()

    save_warehouse_cell(zone, column_no, position, slot_no, customer_name, product, qty, note)
    upsert_customer(customer_name) if customer_name else None
    log_action(session["user"], "更新倉庫格位", "warehouse", f"{zone}-{column_no}-{position}-{slot_no}", data)
    add_notification("warehouse", f"{session['user']}｜更新了倉庫格位", session["user"], data)
    return jsonify({"success": True})


@app.route("/api/warehouse/delete", methods=["POST"])
def api_warehouse_delete():
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    cell_id = data.get("id")
    if cell_id:
        delete_warehouse_cell(int(cell_id))
        log_action(session["user"], "刪除倉庫格位", "warehouse", str(cell_id))
        add_notification("warehouse", f"{session['user']}｜刪除倉庫格位", session["user"], {"id": cell_id})
    return jsonify({"success": True})


# ---------- notifications ----------
@app.route("/api/notifications")
def api_notifications():
    if not require_login():
        return error_response("請先登入", 401)
    unread_only = request.args.get("unread") == "1"
    limit = int(request.args.get("limit", 100))
    items = list_notifications(limit=limit, unread_only=unread_only)
    return jsonify({"success": True, "items": items})


@app.route("/api/notifications/mark_read", methods=["POST"])
def api_notifications_mark_read():
    if not require_login():
        return error_response("請先登入", 401)
    data = json_request()
    mark_notifications_read(data.get("ids") or [])
    return jsonify({"success": True})


# ---------- reconciliation / backups ----------
@app.route("/api/reconciliation")
def api_reconciliation():
    if not require_login():
        return error_response("請先登入", 401)
    return jsonify({"success": True, "items": reconciliation()})


@app.route("/api/backup/run", methods=["POST"])
def api_backup_run():
    if not require_login():
        return error_response("請先登入", 401)
    result = run_daily_backup()
    log_action(session["user"], "手動備份", "backup", "manual")
    add_notification("backup", f"{session['user']}｜已完成備份", session["user"], result)
    return jsonify(result)


@app.route("/api/backup/list")
def api_backup_list():
    if not require_login():
        return error_response("請先登入", 401)
    return jsonify(list_backups())


# ---------- health ----------
@app.route("/health")
def health():
    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
