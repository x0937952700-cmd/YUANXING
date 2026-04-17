
import os
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from difflib import get_close_matches

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///yuanxing.db")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    import psycopg2


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _q(query: str) -> str:
    return query.replace("?", "%s") if USE_POSTGRES else query


def _row_id(row):
    return row[0] if USE_POSTGRES else row["id"]


def _row_value(row, key):
    return row[key] if not USE_POSTGRES else row[key]


@contextmanager
def db_conn():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    db_path = DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def fetchall_dict(cur):
    if USE_POSTGRES:
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    return [dict(r) for r in cur.fetchall()]


def fetchone_dict(cur):
    row = cur.fetchone()
    if not row:
        return None
    if USE_POSTGRES:
        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))
    return dict(row)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    pk = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    tables = [
        f"""CREATE TABLE IF NOT EXISTS users (
            id {pk},
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS settings (
            id {pk},
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            updated_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS customers (
            id {pk},
            customer_name TEXT UNIQUE NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            special_requests TEXT DEFAULT '',
            region TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS inventory (
            id {pk},
            product TEXT NOT NULL,
            quantity INTEGER DEFAULT 0,
            location TEXT DEFAULT '',
            customer_name TEXT DEFAULT '',
            operator TEXT DEFAULT '',
            warehouse_zone TEXT DEFAULT '',
            band_no INTEGER DEFAULT 0,
            row_label TEXT DEFAULT '',
            cell_no INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS orders (
            id {pk},
            customer TEXT NOT NULL,
            product TEXT NOT NULL,
            qty INTEGER NOT NULL,
            status TEXT NOT NULL,
            operator TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS master_orders (
            id {pk},
            customer TEXT NOT NULL,
            product TEXT NOT NULL,
            qty INTEGER NOT NULL,
            operator TEXT DEFAULT '',
            note TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS shipping_records (
            id {pk},
            customer TEXT NOT NULL,
            product TEXT NOT NULL,
            qty INTEGER NOT NULL,
            operator TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            shipped_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS corrections (
            id {pk},
            wrong_text TEXT UNIQUE NOT NULL,
            correct_text TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS image_hashes (
            id {pk},
            image_hash TEXT UNIQUE NOT NULL,
            image_path TEXT DEFAULT '',
            ocr_text TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS logs (
            id {pk},
            username TEXT DEFAULT '',
            action TEXT NOT NULL,
            target_type TEXT DEFAULT '',
            target_name TEXT DEFAULT '',
            detail TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS errors (
            id {pk},
            source TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS notifications (
            id {pk},
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            category TEXT DEFAULT '',
            actor TEXT DEFAULT '',
            target_type TEXT DEFAULT '',
            target_name TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS warehouse_cells (
            id {pk},
            zone TEXT NOT NULL,
            band_no INTEGER NOT NULL,
            row_label TEXT NOT NULL,
            cell_no INTEGER NOT NULL,
            slot_key TEXT UNIQUE NOT NULL,
            customer_name TEXT DEFAULT '',
            product TEXT DEFAULT '',
            quantity INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            updated_at TEXT NOT NULL
        )"""
    ]
    for stmt in tables:
        cur.execute(stmt)
    conn.commit()
    conn.close()


def get_user(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM users WHERE username=?"), (username,))
    row = fetchone_dict(cur)
    conn.close()
    return row


def create_user(username, password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        _q("INSERT INTO users(username,password,created_at) VALUES(?,?,?)"),
        (username, password, now()),
    )
    conn.commit()
    conn.close()


def update_user_password(username, new_password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        _q("UPDATE users SET password=? WHERE username=?"),
        (new_password, username),
    )
    conn.commit()
    conn.close()


def log_action(username, action, target_type="", target_name="", detail=""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        _q("INSERT INTO logs(username,action,target_type,target_name,detail,created_at) VALUES(?,?,?,?,?,?)"),
        (username or "", action, target_type, target_name, detail, now()),
    )
    conn.commit()
    conn.close()


def log_error(source, message):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            _q("INSERT INTO errors(source,message,created_at) VALUES(?,?,?)"),
            (source, str(message), now()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def save_notification(title, message, category="", actor="", target_type="", target_name=""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        _q("INSERT INTO notifications(title,message,category,actor,target_type,target_name,is_read,created_at) VALUES(?,?,?,?,?,?,0,?)"),
        (title, message, category, actor, target_type, target_name, now()),
    )
    conn.commit()
    conn.close()


def list_notifications(limit=100, unread_only=False):
    conn = get_db()
    cur = conn.cursor()
    where = "WHERE is_read=0" if unread_only else ""
    cur.execute(_q(f"SELECT * FROM notifications {where} ORDER BY id DESC LIMIT ?"), (limit,))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def latest_notifications(since_id=0, limit=20):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM notifications WHERE id>? ORDER BY id ASC LIMIT ?"), (since_id, limit))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def mark_notifications_read(ids=None):
    conn = get_db()
    cur = conn.cursor()
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        cur.execute(_q(f"UPDATE notifications SET is_read=1 WHERE id IN ({placeholders})"), tuple(ids))
    else:
        cur.execute(_q("UPDATE notifications SET is_read=1 WHERE is_read=0"))
    conn.commit()
    conn.close()


def unread_notification_count():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT COUNT(*) AS c FROM notifications WHERE is_read=0"))
    row = cur.fetchone()
    count = row[0] if USE_POSTGRES else row["c"]
    conn.close()
    return int(count)


def list_logs(limit=200):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM logs ORDER BY id DESC LIMIT ?"), (limit,))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def list_errors(limit=100):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM errors ORDER BY id DESC LIMIT ?"), (limit,))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def save_correction(wrong, correct):
    if not wrong or not correct or wrong == correct:
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("DELETE FROM corrections WHERE wrong_text=?"), (wrong,))
    cur.execute(
        _q("INSERT INTO corrections(wrong_text,correct_text,updated_at) VALUES(?,?,?)"),
        (wrong, correct, now()),
    )
    conn.commit()
    conn.close()


def get_corrections():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT wrong_text, correct_text FROM corrections")
    rows = fetchall_dict(cur)
    conn.close()
    return {r["wrong_text"]: r["correct_text"] for r in rows}


def save_image_hash(image_hash, image_path="", ocr_text=""):
    conn = get_db()
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute(
            """
            INSERT INTO image_hashes(image_hash,image_path,ocr_text,created_at)
            VALUES(%s,%s,%s,%s)
            ON CONFLICT (image_hash) DO UPDATE SET
                image_path=EXCLUDED.image_path,
                ocr_text=EXCLUDED.ocr_text
            """,
            (image_hash, image_path, ocr_text, now()),
        )
    else:
        cur.execute("DELETE FROM image_hashes WHERE image_hash=?", (image_hash,))
        cur.execute(
            """
            INSERT INTO image_hashes(image_hash,image_path,ocr_text,created_at)
            VALUES(?,?,?,?)
            """,
            (image_hash, image_path, ocr_text, now()),
        )
    conn.commit()
    conn.close()


def image_hash_exists(image_hash):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM image_hashes WHERE image_hash=?"), (image_hash,))
    row = fetchone_dict(cur)
    conn.close()
    return row


def list_inventory():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM inventory ORDER BY updated_at DESC, id DESC"))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def inventory_summary():
    rows = list_inventory()
    products = {}
    for row in rows:
        key = row["product"]
        if key not in products:
            products[key] = {"product": key, "quantity": 0, "locations": set(), "customers": set(), "updated_at": row["updated_at"]}
        products[key]["quantity"] += int(row.get("quantity") or 0)
        if row.get("location"):
            products[key]["locations"].add(row["location"])
        if row.get("customer_name"):
            products[key]["customers"].add(row["customer_name"])
    out = []
    for p in products.values():
        out.append({
            "product": p["product"],
            "quantity": p["quantity"],
            "locations": sorted(list(p["locations"])),
            "customers": sorted(list(p["customers"])),
            "updated_at": p["updated_at"],
            "is_unplaced": len(p["locations"]) == 0,
        })
    return sorted(out, key=lambda x: (-x["quantity"], x["product"]))


def upsert_inventory(product, quantity, location="", customer_name="", operator="", warehouse_zone="", band_no=0, row_label="", cell_no=0):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM inventory WHERE product=? AND COALESCE(location,'')=?"), (product, location or ""))
    row = fetchone_dict(cur)
    if row:
        cur.execute(
            _q("""
            UPDATE inventory
            SET quantity=quantity+?, customer_name=?, operator=?, warehouse_zone=?, band_no=?, row_label=?, cell_no=?, updated_at=?
            WHERE id=?
            """),
            (int(quantity), customer_name or row.get("customer_name",""), operator, warehouse_zone, int(band_no), row_label, int(cell_no), now(), row["id"]),
        )
    else:
        cur.execute(
            _q("""
            INSERT INTO inventory(product,quantity,location,customer_name,operator,warehouse_zone,band_no,row_label,cell_no,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """),
            (product, int(quantity), location, customer_name, operator, warehouse_zone, int(band_no), row_label, int(cell_no), now()),
        )
    conn.commit()
    conn.close()


def save_order(customer, items, operator="", note=""):
    conn = get_db()
    cur = conn.cursor()
    for item in items:
        cur.execute(
            _q("INSERT INTO orders(customer,product,qty,status,operator,note,created_at) VALUES(?,?,?,?,?,?,?)"),
            (customer, item["product"], int(item["quantity"]), "pending", operator, note, now()),
        )
    conn.commit()
    conn.close()
    sync_customer(customer, region="", phone="", address="", special_requests="")


def save_master_order(customer, items, operator="", note=""):
    conn = get_db()
    cur = conn.cursor()
    for item in items:
        product = item["product"]
        qty = int(item["quantity"])
        cur.execute(_q("SELECT * FROM master_orders WHERE customer=? AND product=?"), (customer, product))
        row = fetchone_dict(cur)
        if row:
            cur.execute(
                _q("UPDATE master_orders SET qty=qty+?, operator=?, note=?, updated_at=? WHERE id=?"),
                (qty, operator, note, now(), row["id"]),
            )
        else:
            cur.execute(
                _q("INSERT INTO master_orders(customer,product,qty,operator,note,updated_at) VALUES(?,?,?,?,?,?)"),
                (customer, product, qty, operator, note, now()),
            )
    conn.commit()
    conn.close()
    sync_customer(customer, region="", phone="", address="", special_requests="")


def list_orders(limit=200):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM orders ORDER BY id DESC LIMIT ?"), (limit,))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def list_master_orders(limit=200):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM master_orders ORDER BY id DESC LIMIT ?"), (limit,))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def list_shipping_records(days=None, limit=500):
    conn = get_db()
    cur = conn.cursor()
    if days:
        cur.execute(_q("SELECT * FROM shipping_records WHERE shipped_at >= ? ORDER BY id DESC LIMIT ?"), (days, limit))
        # above is handled by caller with date string
    else:
        cur.execute(_q("SELECT * FROM shipping_records ORDER BY id DESC LIMIT ?"), (limit,))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def deduct_rows_by_product(table_name, customer, product, qty_needed, operator, cur):
    cur.execute(_q(f"SELECT * FROM {table_name} WHERE customer=? AND product=? AND qty>0 ORDER BY id ASC"), (customer, product))
    rows = fetchall_dict(cur)
    remaining = int(qty_needed)
    for row in rows:
        if remaining <= 0:
            break
        use_qty = min(int(row["qty"]), remaining)
        new_qty = int(row["qty"]) - use_qty
        cur.execute(_q(f"UPDATE {table_name} SET qty=?, operator=? WHERE id=?"), (new_qty, operator, row["id"]))
        remaining -= use_qty
    return remaining


def ship_order(customer, items, operator=""):
    conn = get_db()
    cur = conn.cursor()
    try:
        for item in items:
            product = item["product"]
            need = int(item["quantity"])

            cur.execute(_q("SELECT COALESCE(SUM(qty),0) AS c FROM master_orders WHERE customer=? AND product=?"), (customer, product))
            master_total = cur.fetchone()[0] if USE_POSTGRES else cur.fetchone()["c"]
            cur.execute(_q("SELECT COALESCE(SUM(qty),0) AS c FROM orders WHERE customer=? AND product=? AND status='pending'"), (customer, product))
            order_total = cur.fetchone()[0] if USE_POSTGRES else cur.fetchone()["c"]
            cur.execute(_q("SELECT COALESCE(SUM(quantity),0) AS c FROM inventory WHERE product=?"), (product,))
            inv_total = cur.fetchone()[0] if USE_POSTGRES else cur.fetchone()["c"]

            if int(master_total) < need or int(order_total) < need or int(inv_total) < need:
                conn.rollback()
                return {"success": False, "error": f"{product} 庫存不足或單據不足"}

            rem = need
            cur.execute(_q("SELECT * FROM master_orders WHERE customer=? AND product=? ORDER BY id ASC"), (customer, product))
            rows = fetchall_dict(cur)
            for row in rows:
                if rem <= 0:
                    break
                use_qty = min(int(row["qty"]), rem)
                cur.execute(_q("UPDATE master_orders SET qty=qty-?, operator=?, updated_at=? WHERE id=?"), (use_qty, operator, now(), row["id"]))
                rem -= use_qty

            rem = need
            cur.execute(_q("SELECT * FROM orders WHERE customer=? AND product=? AND status='pending' ORDER BY id ASC"), (customer, product))
            rows = fetchall_dict(cur)
            for row in rows:
                if rem <= 0:
                    break
                use_qty = min(int(row["qty"]), rem)
                new_qty = int(row["qty"]) - use_qty
                new_status = "done" if new_qty <= 0 else "pending"
                cur.execute(_q("UPDATE orders SET qty=?, status=?, operator=? WHERE id=?"), (new_qty, new_status, operator, row["id"]))
                rem -= use_qty

            rem = need
            cur.execute(_q("SELECT * FROM inventory WHERE product=? AND quantity>0 ORDER BY quantity DESC, id ASC"), (product,))
            rows = fetchall_dict(cur)
            for row in rows:
                if rem <= 0:
                    break
                use_qty = min(int(row["quantity"]), rem)
                cur.execute(_q("UPDATE inventory SET quantity=quantity-?, updated_at=? WHERE id=?"), (use_qty, now(), row["id"]))
                rem -= use_qty

            detail = f"{customer} | {product} | {need}"
            cur.execute(_q("INSERT INTO shipping_records(customer,product,qty,operator,detail,shipped_at) VALUES(?,?,?,?,?,?)"), (customer, product, need, operator, detail, now()))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        log_error("ship_order", str(e))
        return {"success": False, "error": "出貨失敗"}
    finally:
        conn.close()


def sync_customer(customer_name, region="", phone="", address="", special_requests=""):
    customer_name = (customer_name or "").strip()
    if not customer_name:
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM customers WHERE customer_name=?"), (customer_name,))
    row = fetchone_dict(cur)
    if row:
        cur.execute(
            _q("""
            UPDATE customers SET
                phone=COALESCE(NULLIF(?,''), phone),
                address=COALESCE(NULLIF(?,''), address),
                special_requests=COALESCE(NULLIF(?,''), special_requests),
                region=COALESCE(NULLIF(?,''), region),
                updated_at=?
            WHERE customer_name=?
            """),
            (phone or "", address or "", special_requests or "", region or "", now(), customer_name),
        )
    else:
        cur.execute(
            _q("INSERT INTO customers(customer_name,phone,address,special_requests,region,updated_at) VALUES(?,?,?,?,?,?)"),
            (customer_name, phone or "", address or "", special_requests or "", region or "", now()),
        )
    conn.commit()
    conn.close()


def list_customers():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM customers ORDER BY updated_at DESC, customer_name ASC"))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def update_customer(customer_name, phone="", address="", special_requests="", region=""):
    sync_customer(customer_name, region=region, phone=phone, address=address, special_requests=special_requests)


def search_customers(q="", limit=12):
    customers = [c["customer_name"] for c in list_customers()]
    q = (q or "").strip()
    if not q:
        return customers[:limit]
    low = [c for c in customers if q in c]
    if low:
        return low[:limit]
    matches = get_close_matches(q, customers, n=limit, cutoff=0.2)
    return matches[:limit]


def save_warehouse_cell(zone, band_no, row_label, cell_no, customer_name="", product="", quantity=0, note=""):
    slot_key = f"{zone}-{band_no}-{row_label}-{cell_no}"
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM warehouse_cells WHERE slot_key=?"), (slot_key,))
    row = fetchone_dict(cur)
    if row:
        cur.execute(
            _q("""
            UPDATE warehouse_cells
            SET customer_name=?, product=?, quantity=?, note=?, updated_at=?
            WHERE slot_key=?
            """),
            (customer_name, product, int(quantity), note, now(), slot_key),
        )
    else:
        cur.execute(
            _q("""
            INSERT INTO warehouse_cells(zone,band_no,row_label,cell_no,slot_key,customer_name,product,quantity,note,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """),
            (zone, int(band_no), row_label, int(cell_no), slot_key, customer_name, product, int(quantity), note, now()),
        )
    # keep inventory location in sync if product exists
    if product:
        cur.execute(_q("UPDATE inventory SET location=?, customer_name=?, warehouse_zone=?, band_no=?, row_label=?, cell_no=?, updated_at=? WHERE product=?"),
                    (slot_key, customer_name, zone, int(band_no), row_label, int(cell_no), now(), product))
    conn.commit()
    conn.close()


def list_warehouse_cells(zone=None):
    conn = get_db()
    cur = conn.cursor()
    if zone:
        cur.execute(_q("SELECT * FROM warehouse_cells WHERE zone=? ORDER BY band_no ASC, row_label ASC, cell_no ASC"), (zone,))
    else:
        cur.execute(_q("SELECT * FROM warehouse_cells ORDER BY zone ASC, band_no ASC, row_label ASC, cell_no ASC"))
    rows = fetchall_dict(cur)
    conn.close()
    return rows


def warehouse_grid(zone):
    cells = list_warehouse_cells(zone)
    grid = {}
    for cell in cells:
        grid[(cell["band_no"], cell["row_label"], cell["cell_no"])] = cell
    bands = []
    for band in range(1, 7):
        bands.append({
            "band_no": band,
            "front": [grid.get((band, "front", c), None) for c in range(1, 11)],
            "back": [grid.get((band, "back", c), None) for c in range(1, 11)],
        })
    return bands


def unplaced_inventory_products():
    items = inventory_summary()
    return [x for x in items if x["is_unplaced"] or not x["locations"]]


def reconcile_data():
    inv = inventory_summary()
    orders = list_orders()
    masters = list_master_orders()
    ships = list_shipping_records()

    inv_map = {i["product"]: i["quantity"] for i in inv}
    order_map = {}
    for row in orders:
        if row["status"] == "pending":
            key = (row["customer"], row["product"])
            order_map[key] = order_map.get(key, 0) + int(row["qty"])

    master_map = {}
    for row in masters:
        key = (row["customer"], row["product"])
        master_map[key] = master_map.get(key, 0) + int(row["qty"])

    ship_map = {}
    for row in ships:
        key = (row["customer"], row["product"])
        ship_map[key] = ship_map.get(key, 0) + int(row["qty"])

    discrepancies = []
    for key, qty in master_map.items():
        customer, product = key
        order_qty = order_map.get(key, 0)
        shipped = ship_map.get(key, 0)
        inv_qty = inv_map.get(product, 0)
        if not (qty == order_qty == shipped):
            discrepancies.append({
                "customer": customer,
                "product": product,
                "master_qty": qty,
                "order_qty": order_qty,
                "ship_qty": shipped,
                "inventory_qty": inv_qty,
            })
    return discrepancies


def dashboard_summary():
    inv = inventory_summary()
    orders = list_orders()
    ships = list_shipping_records()
    masters = list_master_orders()
    today = datetime.now().strftime("%Y-%m-%d")
    today_logs = [l for l in list_logs(1000) if l["created_at"].startswith(today)]
    today_ships = [s for s in ships if s["shipped_at"].startswith(today)]
    today_notifications = [n for n in list_notifications(1000) if n["created_at"].startswith(today)]
    return {
        "inventory_count": len(inv),
        "order_count": len(orders),
        "master_count": len(masters),
        "ship_count": len(ships),
        "today_ship_count": len(today_ships),
        "unplaced_count": sum(1 for x in inv if x["is_unplaced"]),
        "anomaly_count": len(reconcile_data()),
        "unread_notifications": unread_notification_count(),
        "today_logs": today_logs[:20],
        "today_notifications": today_notifications[:20],
        "unplaced_items": [x for x in inv if x["is_unplaced"]][:20],
    }


def save_setting(key, value):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("DELETE FROM settings WHERE key=?"), (key,))
    cur.execute(_q("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)"), (key, value, now()))
    conn.commit()
    conn.close()


def get_setting(key, default=""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT value FROM settings WHERE key=?"), (key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return default
    return row[0] if USE_POSTGRES else row["value"]


def list_settings():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(_q("SELECT * FROM settings ORDER BY key ASC"))
    rows = fetchall_dict(cur)
    conn.close()
    return rows
