import os
import json
import sqlite3
from datetime import datetime, date
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///warehouse.db")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    import psycopg2


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return date.today().isoformat()


def sql(q: str) -> str:
    return q.replace("?", "%s") if USE_POSTGRES else q


def connect():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    db_path = DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    if row is None:
        return None
    if USE_POSTGRES:
        return dict(row)
    return dict(row)


def rows_to_dicts(rows):
    return [row_to_dict(r) for r in rows]


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def _fetchall(cur):
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    return [dict(r) for r in cur.fetchall()]


def _fetchone(cur):
    row = cur.fetchone()
    if not row:
        return None
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    return dict(row)


def query_all(query, params=()):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql(query), params)
        return _fetchall(cur)


def query_one(query, params=()):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql(query), params)
        return _fetchone(cur)


def execute(query, params=(), commit=True):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql(query), params)
        if commit:
            conn.commit()
        return cur


def init_db():
    pk = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    unique = "UNIQUE"
    text = "TEXT"
    integer = "INTEGER"

    table_sql = [
        f"""
        CREATE TABLE IF NOT EXISTS users (
            id {pk},
            username {text} {unique},
            password {text} NOT NULL,
            created_at {text},
            updated_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS settings (
            key {text} PRIMARY KEY,
            value {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS customers (
            id {pk},
            name {text} {unique},
            zone {text},
            phone {text},
            address {text},
            note {text},
            created_at {text},
            updated_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS inventory (
            id {pk},
            product {text},
            quantity {integer} DEFAULT 0,
            location {text},
            customer_name {text},
            operator {text},
            note {text},
            updated_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS orders (
            id {pk},
            customer_name {text},
            product {text},
            qty {integer},
            status {text},
            operator {text},
            created_at {text},
            updated_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS master_orders (
            id {pk},
            customer_name {text},
            product {text},
            qty {integer},
            operator {text},
            created_at {text},
            updated_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS shipping_records (
            id {pk},
            customer_name {text},
            product {text},
            qty {integer},
            operator {text},
            deducted_master {integer} DEFAULT 0,
            deducted_order {integer} DEFAULT 0,
            deducted_inventory {integer} DEFAULT 0,
            details_json {text},
            shipped_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS corrections (
            id {pk},
            wrong_text {text} {unique},
            correct_text {text},
            updated_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS image_hashes (
            id {pk},
            image_hash {text} {unique},
            created_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS logs (
            id {pk},
            username {text},
            action {text},
            target_type {text},
            target_name {text},
            meta_json {text},
            created_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS notifications (
            id {pk},
            kind {text},
            message {text},
            username {text},
            meta_json {text},
            read_flag {integer} DEFAULT 0,
            created_at {text}
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS warehouse_cells (
            id {pk},
            zone {text},
            column_no {integer},
            position {text},
            slot_no {integer},
            customer_name {text},
            product {text},
            qty {integer} DEFAULT 0,
            note {text},
            updated_at {text},
            UNIQUE(zone, column_no, position, slot_no)
        )
        """
    ]

    with get_db() as conn:
        cur = conn.cursor()
        for ddl in table_sql:
            cur.execute(ddl)
        if USE_POSTGRES:
            # create default settings only if not present
            pass
        conn.commit()


# ---------- auth ----------
def get_user(username):
    return query_one("SELECT * FROM users WHERE username=?", (username,))


def create_user(username, password):
    execute(
        "INSERT INTO users(username, password, created_at, updated_at) VALUES(?,?,?,?)",
        (username, password, now(), now())
    )


def update_user_password(username, new_password):
    execute(
        "UPDATE users SET password=?, updated_at=? WHERE username=?",
        (new_password, now(), username)
    )


# ---------- settings ----------
def get_setting(key, default=None):
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else default


def set_setting(key, value):
    with get_db() as conn:
        cur = conn.cursor()
        existing = query_one("SELECT key FROM settings WHERE key=?", (key,))
        if existing:
            cur.execute(sql("UPDATE settings SET value=? WHERE key=?"), (value, key))
        else:
            cur.execute(sql("INSERT INTO settings(key,value) VALUES(?,?)"), (key, value))
        conn.commit()


# ---------- logging / notifications ----------
def log_action(username, action, target_type="", target_name="", meta=None):
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    execute(
        "INSERT INTO logs(username, action, target_type, target_name, meta_json, created_at) VALUES(?,?,?,?,?,?)",
        (username, action, target_type, target_name, meta_json, now())
    )


def add_notification(kind, message, username="", meta=None):
    meta_json = json.dumps(meta or {}, ensure_ascii=False)
    execute(
        "INSERT INTO notifications(kind, message, username, meta_json, created_at) VALUES(?,?,?,?,?)",
        (kind, message, username, meta_json, now())
    )


def mark_notifications_read(notification_ids):
    if not notification_ids:
        return
    with get_db() as conn:
        cur = conn.cursor()
        for nid in notification_ids:
            cur.execute(sql("UPDATE notifications SET read_flag=1 WHERE id=?"), (nid,))
        conn.commit()


def list_notifications(limit=100, unread_only=False):
    q = "SELECT * FROM notifications"
    params = []
    if unread_only:
        q += " WHERE read_flag=0"
    q += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return query_all(q, tuple(params))


def get_today_notification_count():
    today = today_str()
    return query_one(
        "SELECT COUNT(*) AS c FROM notifications WHERE created_at LIKE ?",
        (today + "%",)
    )["c"]


# ---------- corrections ----------
def save_correction(wrong, correct):
    if not wrong or not correct:
        return
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql("DELETE FROM corrections WHERE wrong_text=?"), (wrong,))
        cur.execute(
            sql("INSERT INTO corrections(wrong_text, correct_text, updated_at) VALUES(?,?,?)"),
            (wrong, correct, now())
        )
        conn.commit()


def get_corrections():
    rows = query_all("SELECT wrong_text, correct_text FROM corrections ORDER BY id DESC")
    return {r["wrong_text"]: r["correct_text"] for r in rows}


# ---------- customers ----------
def upsert_customer(name, zone="未分類", phone="", address="", note=""):
    if not name:
        return
    row = query_one("SELECT id FROM customers WHERE name=?", (name,))
    if row:
        execute(
            "UPDATE customers SET zone=?, phone=?, address=?, note=?, updated_at=? WHERE name=?",
            (zone, phone, address, note, now(), name)
        )
    else:
        execute(
            "INSERT INTO customers(name, zone, phone, address, note, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (name, zone, phone, address, note, now(), now())
        )


def list_customers():
    return query_all("SELECT * FROM customers ORDER BY zone, name")


def suggest_customers(keyword):
    keyword = (keyword or "").strip()
    if not keyword:
        return list_customers()
    return query_all(
        "SELECT * FROM customers WHERE name LIKE ? ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END, name LIMIT 20",
        (f"%{keyword}%", f"{keyword}%")
    )


def update_customer(customer_id, **fields):
    allowed = ["name", "zone", "phone", "address", "note"]
    pieces = []
    params = []
    for k in allowed:
        if k in fields:
            pieces.append(f"{k}=?")
            params.append(fields[k])
    if not pieces:
        return
    pieces.append("updated_at=?")
    params.append(now())
    params.append(customer_id)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql(f"UPDATE customers SET {', '.join(pieces)} WHERE id=?"), tuple(params))
        conn.commit()


# ---------- inventory ----------
def upsert_inventory(product, quantity, location="", customer_name="", operator="", note=""):
    if not product:
        return
    row = query_one("SELECT id, quantity FROM inventory WHERE product=? AND location=?", (product, location))
    if row:
        execute(
            "UPDATE inventory SET quantity = quantity + ?, customer_name=?, operator=?, note=?, updated_at=? WHERE id=?",
            (int(quantity), customer_name, operator, note, now(), row["id"])
        )
    else:
        execute(
            "INSERT INTO inventory(product, quantity, location, customer_name, operator, note, updated_at) VALUES(?,?,?,?,?,?,?)",
            (product, int(quantity), location, customer_name, operator, note, now())
        )


def list_inventory():
    rows = query_all("SELECT * FROM inventory ORDER BY updated_at DESC, product")
    # enrich with warehouse placement
    cells = query_all("SELECT product, SUM(qty) AS placed_qty FROM warehouse_cells WHERE product IS NOT NULL AND product != '' GROUP BY product")
    placed = {r["product"]: int(r["placed_qty"] or 0) for r in cells}
    for r in rows:
        r["placed_qty"] = placed.get(r["product"], 0)
        r["unplaced_qty"] = max(int(r.get("quantity") or 0) - r["placed_qty"], 0)
    return rows


# ---------- orders ----------
def save_order(customer_name, items, operator):
    upsert_customer(customer_name)
    created = []
    for item in items:
        product = item.get("product") or item.get("product_name") or ""
        qty = int(item.get("quantity") or 1)
        execute(
            "INSERT INTO orders(customer_name, product, qty, status, operator, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (customer_name, product, qty, "pending", operator, now(), now())
        )
        created.append({"product": product, "qty": qty})
    return created


def list_orders():
    return query_all("SELECT * FROM orders ORDER BY id DESC")


def save_master_order(customer_name, items, operator):
    upsert_customer(customer_name)
    for item in items:
        product = item.get("product") or item.get("product_name") or ""
        qty = int(item.get("quantity") or 1)
        row = query_one("SELECT id, qty FROM master_orders WHERE customer_name=? AND product=?", (customer_name, product))
        if row:
            execute(
                "UPDATE master_orders SET qty = qty + ?, operator=?, updated_at=? WHERE id=?",
                (qty, operator, now(), row["id"])
            )
        else:
            execute(
                "INSERT INTO master_orders(customer_name, product, qty, operator, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                (customer_name, product, qty, operator, now(), now())
            )


def list_master_orders():
    return query_all("SELECT * FROM master_orders ORDER BY id DESC")


# ---------- shipping ----------
def list_shipping_records(days=None):
    q = "SELECT * FROM shipping_records"
    params = []
    if days:
        q += " WHERE shipped_at >= ?"
        # date-like filtering via string prefix.
        from datetime import datetime, timedelta
        start = (datetime.now() - timedelta(days=int(days))).strftime("%Y-%m-%d")
        params.append(start)
    q += " ORDER BY id DESC"
    return query_all(q, tuple(params))


# ---------- warehouse cells ----------
def list_warehouse_cells(zone=None):
    q = "SELECT * FROM warehouse_cells"
    params = []
    if zone:
        q += " WHERE zone=?"
        params.append(zone)
    q += " ORDER BY zone, column_no, slot_no"
    return query_all(q, tuple(params))


def save_warehouse_cell(zone, column_no, position, slot_no, customer_name="", product="", qty=0, note=""):
    row = query_one(
        "SELECT id FROM warehouse_cells WHERE zone=? AND column_no=? AND position=? AND slot_no=?",
        (zone, int(column_no), position, int(slot_no))
    )
    if row:
        execute(
            "UPDATE warehouse_cells SET customer_name=?, product=?, qty=?, note=?, updated_at=? WHERE id=?",
            (customer_name, product, int(qty), note, now(), row["id"])
        )
    else:
        execute(
            "INSERT INTO warehouse_cells(zone, column_no, position, slot_no, customer_name, product, qty, note, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (zone, int(column_no), position, int(slot_no), customer_name, product, int(qty), note, now())
        )


def delete_warehouse_cell(cell_id):
    execute("DELETE FROM warehouse_cells WHERE id=?", (cell_id,))


def warehouse_search(keyword):
    keyword = (keyword or "").strip()
    if not keyword:
        return list_warehouse_cells()
    return query_all(
        """
        SELECT * FROM warehouse_cells
        WHERE zone LIKE ? OR CAST(column_no AS TEXT) LIKE ? OR position LIKE ? OR CAST(slot_no AS TEXT) LIKE ?
           OR customer_name LIKE ? OR product LIKE ?
        ORDER BY zone, column_no, slot_no
        """,
        (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", f"%{keyword}%")
    )


# ---------- dashboard / reconciliation ----------
def get_unplaced_products():
    rows = list_inventory()
    return [r for r in rows if int(r.get("unplaced_qty") or 0) > 0]


def reconciliation():
    inventory = query_all("SELECT product, SUM(quantity) AS qty FROM inventory GROUP BY product")
    orders = query_all("SELECT product, SUM(qty) AS qty FROM orders GROUP BY product")
    masters = query_all("SELECT product, SUM(qty) AS qty FROM master_orders GROUP BY product")
    shipped = query_all("SELECT product, SUM(qty) AS qty FROM shipping_records GROUP BY product")

    idx = {}
    for bucket, name in [(inventory, "inventory"), (orders, "orders"), (masters, "masters"), (shipped, "shipped")]:
        for r in bucket:
            idx.setdefault(r["product"], {"product": r["product"], "inventory": 0, "orders": 0, "masters": 0, "shipped": 0})
            idx[r["product"]][name] = int(r["qty"] or 0)

    diffs = []
    for v in idx.values():
        # simple anomaly if order/master/shipped diverge with inventory
        if not (v["orders"] == v["masters"] == v["shipped"] or v["inventory"] >= 0):
            pass
        expected = v["inventory"] - v["shipped"]
        diffs.append({**v, "expected_after_ship": expected, "diff_orders_masters": v["orders"] - v["masters"]})
    return sorted(diffs, key=lambda x: x["product"])


def dashboard_summary():
    today = today_str()
    new_count = query_one(
        "SELECT COUNT(*) AS c FROM logs WHERE created_at LIKE ? AND (action LIKE '新增%' OR action LIKE '建立%' OR action LIKE '%新增%')",
        (today + "%",)
    )["c"]
    ship_count = query_one(
        "SELECT COUNT(*) AS c FROM shipping_records WHERE shipped_at LIKE ?",
        (today + "%",)
    )["c"]
    unplaced = len(get_unplaced_products())
    anomalies = len([d for d in reconciliation() if (d["orders"] != d["masters"]) or (d["inventory"] < d["shipped"])])
    unread = query_one("SELECT COUNT(*) AS c FROM notifications WHERE read_flag=0")["c"]
    return {
        "new_count": new_count,
        "ship_count": ship_count,
        "unplaced_count": unplaced,
        "anomaly_count": anomalies,
        "unread_notifications": unread,
    }
