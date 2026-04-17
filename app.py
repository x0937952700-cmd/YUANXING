
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory, Response
from datetime import timedelta, datetime
from functools import wraps
import os
import hashlib
import json
from PIL import Image

from db import (
    init_db, get_user, create_user, update_password, log_action,
    save_inventory_item, list_inventory, save_order, save_master_order,
    ship_order, get_shipping_records, save_correction, log_error,
    save_image_hash, image_hash_exists, upsert_customer, get_customers,
    get_customer, warehouse_get_cells, warehouse_save_cell, warehouse_move_item,
    inventory_summary, warehouse_summary, list_backups, get_orders, get_master_orders,
    get_activity_logs, get_today_error_count, get_today_shipping_qty,
    row_to_dict, get_db, sql, rows_to_dict, fetchone_dict, now
)
from ocr import process_ocr_text, parse_ocr_text
from backup import run_daily_backup

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "warehouse-secret-key")
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic", "gif"}
MAX_UPLOAD_SIZE = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE

init_db()

PUBLIC_PATHS = {
    "login", "api_login", "health", "static"
}

def current_username():
    return session.get("user", "")

def require_login():
    return bool(current_username())

def login_required_json(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not require_login():
            return jsonify(success=False, error="請先登入"), 401
        return f(*args, **kwargs)
    return wrapper

@app.before_request
def protect_pages():
    path = request.path
    if path.startswith("/static/") or path in ("/health",):
        return None
    public = [
        "/login", "/api/login", "/api/health"
    ]
    if path in public:
        return None
    if not require_login() and path not in ("/",):
        # Let / redirect to login
        if path.startswith("/api/"):
            return jsonify(success=False, error="請先登入"), 401
        return redirect(url_for("login_page"))
    return None

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def error_response(msg, code=400):
    return jsonify({"success": False, "error": msg}), code

def compress_image(path):
    try:
        img = Image.open(path)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if img.width > 1800:
            ratio = 1800 / float(img.width)
            img = img.resize((1800, int(img.height * ratio)))
        img.save(path, "JPEG", quality=78, optimize=True)
    except Exception as e:
        log_error("compress_image", str(e))

def parse_lines_to_items(text):
    parsed = parse_ocr_text(text)
    return parsed["items"], parsed["text"]

def grouped_inventory():
    return inventory_summary()

def customer_groups():
    customers = get_customers()
    groups = {"北區": [], "中區": [], "南區": []}
    for c in customers:
        region = c.get("region") or "北區"
        if region not in groups:
            region = "北區"
        groups[region].append(c)
    return groups

@app.route('/manifest.webmanifest')
def manifest_webmanifest():
    return send_from_directory('static', 'manifest.webmanifest', mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')


@app.route("/")
def home():
    if not require_login():
        return redirect(url_for("login_page"))
    return render_template("index.html", username=current_username(), title="沅興木業")

@app.route("/login")
def login_page():
    if require_login():
        return redirect(url_for("home"))
    return render_template("login.html", title="登入")

@app.route("/settings")
def settings_page():
    return render_template("settings.html", username=current_username(), title="設定")

@app.route("/inventory")
def inventory_page():
    return render_template("module.html", module_key="inventory", title="庫存", username=current_username())

@app.route("/orders")
def orders_page():
    return render_template("module.html", module_key="orders", title="訂單", username=current_username())

@app.route("/master-order")
def master_order_page():
    return render_template("module.html", module_key="master_order", title="總單", username=current_username())

@app.route("/ship")
def ship_page():
    return render_template("module.html", module_key="ship", title="出貨", username=current_username())

@app.route("/shipping-query")
def shipping_query_page():
    return render_template("module.html", module_key="shipping_query", title="出貨查詢", username=current_username())

@app.route("/warehouse")
def warehouse_page():
    return render_template("module.html", module_key="warehouse", title="倉庫圖", username=current_username())

@app.route("/customers")
def customers_page():
    return render_template("module.html", module_key="customers", title="客戶資料", username=current_username())

@app.route("/api/login", methods=["POST"])
def api_login():
    try:
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or data.get("name") or "").strip()
        password = (data.get("password") or "").strip()
        if not username or not password:
            return error_response("帳號密碼不可空白")
        user = get_user(username)
        if not user:
            create_user(username, password)
            log_action(username, "建立帳號")
        elif user["password"] != password:
            return error_response("密碼錯誤")
        session.permanent = True
        session["user"] = username
        log_action(username, "登入系統")
        return jsonify(success=True, username=username)
    except Exception as e:
        log_error("api_login", str(e))
        return error_response("登入失敗")

@app.route("/api/logout", methods=["POST"])
@login_required_json
def api_logout():
    user = current_username()
    session.clear()
    try:
        log_action(user, "登出系統")
    except Exception:
        pass
    return jsonify(success=True)

@app.route("/api/change_password", methods=["POST"])
@login_required_json
def api_change_password():
    try:
        data = request.get_json(silent=True) or {}
        old_password = (data.get("old_password") or "").strip()
        new_password = (data.get("new_password") or "").strip()
        confirm_password = (data.get("confirm_password") or "").strip()
        user = get_user(current_username())
        if not user or user["password"] != old_password:
            return error_response("舊密碼錯誤")
        if not new_password or len(new_password) < 4:
            return error_response("新密碼至少 4 碼")
        if new_password != confirm_password:
            return error_response("兩次密碼不一致")
        update_password(current_username(), new_password)
        log_action(current_username(), "修改密碼")
        return jsonify(success=True)
    except Exception as e:
        log_error("change_password", str(e))
        return error_response("修改失敗")

@app.route("/api/upload_ocr", methods=["POST"])
@login_required_json
def api_upload_ocr():
    try:
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
        confidence = int(result.get("confidence", 0))
        log_action(current_username(), f"OCR辨識｜信心值:{confidence}%")
        return jsonify(success=True, text=result.get("text", ""), items=result.get("items", []), confidence=confidence,
                       warning=("辨識信心偏低，請確認內容" if confidence < 80 else ""), sync_time=int(os.path.getmtime(path)))
    except Exception as e:
        log_error("upload_ocr", str(e))
        return error_response("OCR辨識失敗")

@app.route("/api/save_correction", methods=["POST"])
@login_required_json
def api_save_correction():
    try:
        data = request.get_json(silent=True) or {}
        wrong = (data.get("wrong_text") or "").strip()
        correct = (data.get("correct_text") or "").strip()
        if wrong and correct and wrong != correct:
            save_correction(wrong, correct)
            log_action(current_username(), f"修正OCR {wrong}->{correct}")
        return jsonify(success=True)
    except Exception as e:
        log_error("save_correction", str(e))
        return error_response("儲存失敗")

def _parse_items_from_request(data):
    items = data.get("items") or []
    if items:
        cleaned = []
        for it in items:
            qty = int(it.get("qty", 0))
            if qty <= 0:
                continue
            cleaned.append({
                "product_text": it.get("product_text") or it.get("product") or "",
                "product_code": it.get("product_code") or "",
                "qty": qty
            })
        return cleaned
    text = data.get("ocr_text") or data.get("text") or ""
    parsed_items, _ = parse_lines_to_items(text)
    return [{"product_text": it["product_text"], "product_code": it.get("product_code", ""), "qty": int(it["qty"])} for it in parsed_items]

@app.route("/api/inventory", methods=["GET", "POST"])
@login_required_json
def api_inventory():
    try:
        if request.method == "GET":
            return jsonify(success=True, items=grouped_inventory())
        data = request.get_json(silent=True) or {}
        items = _parse_items_from_request(data)
        operator = current_username()
        location = (data.get("location") or "").strip()
        customer_name = (data.get("customer_name") or "").strip()
        for it in items:
            save_inventory_item(it["product_text"], it.get("product_code", ""), int(it["qty"]), location, customer_name, operator, data.get("ocr_text", ""))
        log_action(operator, f"建立庫存｜客戶:{customer_name or '未指定'}｜位置:{location or '未指定'}｜商品:{'、'.join([it.get('product_text', '') for it in items[:3]])}")
        return jsonify(success=True, items=grouped_inventory())
    except Exception as e:
        log_error("inventory", str(e))
        return error_response("建立失敗")

@app.route("/api/orders", methods=["GET", "POST"])
@login_required_json
def api_orders():
    try:
        if request.method == "GET":
            return jsonify(success=True, items=get_orders())
        data = request.get_json(silent=True) or {}
        items = _parse_items_from_request(data)
        customer_name = (data.get("customer_name") or "").strip()
        if not customer_name:
            return error_response("請輸入客戶名稱")
        save_order(customer_name, items, current_username())
        log_action(current_username(), f"建立訂單｜客戶:{customer_name}｜商品:{'、'.join([it.get('product_text', '') for it in items[:3]])}")
        return jsonify(success=True, items=get_orders())
    except Exception as e:
        log_error("orders", str(e))
        return error_response("訂單建立失敗")

@app.route("/api/master_orders", methods=["GET", "POST"])
@login_required_json
def api_master_orders():
    try:
        if request.method == "GET":
            return jsonify(success=True, items=get_master_orders())
        data = request.get_json(silent=True) or {}
        items = _parse_items_from_request(data)
        customer_name = (data.get("customer_name") or "").strip()
        if not customer_name:
            return error_response("請輸入客戶名稱")
        save_master_order(customer_name, items, current_username())
        log_action(current_username(), f"更新總單｜客戶:{customer_name}｜商品:{'、'.join([it.get('product_text', '') for it in items[:3]])}")
        return jsonify(success=True, items=get_master_orders())
    except Exception as e:
        log_error("master_orders", str(e))
        return error_response("總單失敗")

@app.route("/api/ship", methods=["POST"])
@login_required_json
def api_ship():
    try:
        data = request.get_json(silent=True) or {}
        items = _parse_items_from_request(data)
        customer_name = (data.get("customer_name") or "").strip()
        if not customer_name:
            return error_response("請輸入客戶名稱")
        # confirm ship button required from frontend
        result = ship_order(customer_name, items, current_username())
        if result.get("success"):
            log_action(current_username(), f"完成出貨｜客戶:{customer_name}｜商品:{'、'.join([it.get('product_text', '') for it in items[:3]])}")
        return jsonify(result)
    except Exception as e:
        log_error("ship", str(e))
        return error_response("出貨失敗")

@app.route("/api/shipping_records", methods=["GET"])
@login_required_json
def api_shipping_records():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    rows = get_shipping_records(start_date=start_date, end_date=end_date)
    return jsonify(success=True, records=rows)

@app.route("/api/customers", methods=["GET", "POST"])
@login_required_json
def api_customers():
    try:
        if request.method == "GET":
            return jsonify(success=True, items=get_customers())
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return error_response("請輸入客戶名稱")
        upsert_customer(
            name,
            phone=(data.get("phone") or "").strip(),
            address=(data.get("address") or "").strip(),
            notes=(data.get("notes") or "").strip(),
            region=(data.get("region") or "北區").strip()
        )
        log_action(current_username(), f"儲存客戶｜{name}｜區域:{data.get('region') or '北區'}")
        return jsonify(success=True, items=get_customers())
    except Exception as e:
        log_error("customers", str(e))
        return error_response("客戶儲存失敗")

@app.route("/api/customers/<name>", methods=["GET"])
@login_required_json
def api_customer_detail(name):
    row = get_customer(name)
    return jsonify(success=True, item=row)

@app.route("/api/warehouse", methods=["GET"])
@login_required_json
def api_warehouse():
    return jsonify(success=True, zones=warehouse_summary(), cells=warehouse_get_cells())

@app.route("/api/warehouse/cell", methods=["POST"])
@login_required_json
def api_warehouse_cell():
    try:
        data = request.get_json(silent=True) or {}
        zone = data.get("zone")
        column_index = int(data.get("column_index"))
        slot_type = data.get("slot_type")
        slot_number = int(data.get("slot_number"))
        items = data.get("items") or []
        note = data.get("note") or ""
        warehouse_save_cell(zone, column_index, slot_type, slot_number, items, note)
        log_action(current_username(), f"更新倉庫格位｜{zone}{column_index}-{slot_type}-{slot_number}")
        return jsonify(success=True, zones=warehouse_summary())
    except Exception as e:
        log_error("warehouse_cell", str(e))
        return error_response("格位更新失敗")

@app.route("/api/warehouse/move", methods=["POST"])
@login_required_json
def api_warehouse_move():
    try:
        data = request.get_json(silent=True) or {}
        from_key = data.get("from_key")
        to_key = data.get("to_key")
        product_text = data.get("product_text")
        qty = int(data.get("qty", 1))
        if not (from_key and to_key and product_text):
            return error_response("缺少參數")
        result = warehouse_move_item(tuple(from_key), tuple(to_key), product_text, qty)
        if result.get("success"):
            log_action(current_username(), f"拖曳商品｜{product_text}｜{from_key[0]}{from_key[1]}-{from_key[2]}-{from_key[3]}→{to_key[0]}{to_key[1]}-{to_key[2]}-{to_key[3]}")
        return jsonify(result)
    except Exception as e:
        log_error("warehouse_move", str(e))
        return error_response("拖曳失敗")

@app.route("/api/warehouse/search")
@login_required_json
def api_warehouse_search():
    q = (request.args.get("q") or "").strip()
    cells = warehouse_get_cells()
    matched = []
    for cell in cells:
        try:
            items = json.loads(cell.get("items_json") or "[]")
        except Exception:
            items = []
        for it in items:
            hay = f"{cell['zone']} {cell['column_index']} {cell['slot_type']} {cell['slot_number']} {it.get('product_text','')} {it.get('customer_name','')}"
            if not q or q.lower() in hay.lower():
                matched.append({"cell": cell, "item": it})
                break
    return jsonify(success=True, items=matched)

@app.route("/api/warehouse/available-items", methods=["GET"])
@login_required_json
def api_warehouse_available_items():
    inv = inventory_summary()
    options = [r for r in inv if int(r.get("unplaced_qty", 0)) > 0]
    return jsonify(success=True, items=options)


@app.route("/api/customer-items", methods=["GET"])
@login_required_json
def api_customer_items():
    name = (request.args.get("name") or "").strip()
    inv = list_inventory()
    orders = get_orders()
    masters = get_master_orders()
    items = []
    if name:
        for row in orders:
            if row.get("customer_name") == name:
                items.append({"source": "訂單", **row})
        for row in masters:
            if row.get("customer_name") == name:
                items.append({"source": "總單", **row})
        for row in inv:
            if row.get("customer_name") == name:
                items.append({"source": "庫存", **row})
    else:
        items = []
    return jsonify(success=True, items=items)


@app.route("/activity")
def activity_page():
    return render_template("module.html", module_key="activity", title="今日異動", username=current_username())


def _today_date():
    return now()[:10]


def _today_errors_feed():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM errors WHERE substr(created_at,1,10) = ? ORDER BY id DESC"), (_today_date(),))
    rows = rows_to_dict(cur)
    conn.close()
    return rows


def _today_activity_summary(seen_after=None):
    logs = get_activity_logs(limit=300, today_only=True)
    inventory_rows = inventory_summary()
    unplaced_qty = sum(int(r.get('unplaced_qty', 0)) for r in inventory_rows)
    shipping_qty = get_today_shipping_qty()
    errors = _today_errors_feed()
    log_additions = sum(1 for r in logs if str(r.get('action', '')).startswith(('建立', '儲存', '更新')))
    error_like = sum(1 for r in logs if ('失敗' in str(r.get('action', ''))) or ('錯誤' in str(r.get('action', ''))))
    latest = logs[0]['created_at'] if logs else ''
    if seen_after:
        unread = sum(1 for r in logs if str(r.get('created_at', '')) > seen_after) + sum(1 for e in errors if str(e.get('created_at', '')) > seen_after)
    else:
        unread = len(logs) + len(errors)
    return {
        'today_new': int(log_additions),
        'today_shipping_qty': int(shipping_qty),
        'unplaced_qty': int(unplaced_qty),
        'today_errors': int(len(errors) + error_like),
        'unread': int(unread),
        'latest': latest,
    }


@app.route("/api/activity/summary", methods=["GET"])
@login_required_json
def api_activity_summary():
    seen_after = (request.args.get('seen_after') or '').strip() or None
    return jsonify(success=True, summary=_today_activity_summary(seen_after))


@app.route("/api/activity/feed", methods=["GET"])
@login_required_json
def api_activity_feed():
    limit = int(request.args.get('limit', 60) or 60)
    logs = get_activity_logs(limit=limit, today_only=True)
    errors = _today_errors_feed()
    feed = []
    for row in logs:
        feed.append({
            'kind': 'log',
            'username': row.get('username', ''),
            'action': row.get('action', ''),
            'created_at': row.get('created_at', ''),
        })
    for row in errors:
        feed.append({
            'kind': 'error',
            'username': row.get('source', '系統'),
            'action': f"異常｜{row.get('message', '')}",
            'created_at': row.get('created_at', ''),
        })
    feed.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    return jsonify(success=True, items=feed[:limit], summary=_today_activity_summary())


@app.route("/api/backup", methods=["POST", "GET"])
@login_required_json
def api_backup():
    return jsonify(run_daily_backup())

@app.route("/api/backups", methods=["GET"])
@login_required_json
def api_backups():
    return jsonify(list_backups())

@app.route("/health")
def health():
    return "OK"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
