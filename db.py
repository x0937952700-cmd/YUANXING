
import os
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///warehouse.db")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    import psycopg2

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sql(query: str) -> str:
    return query.replace("?", "%s") if USE_POSTGRES else query

def _sqlite_path():
    return DATABASE_URL.replace("sqlite:///", "")

def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    conn = sqlite3.connect(_sqlite_path())
    conn.row_factory = sqlite3.Row
    return conn

def row_to_dict(row):
    if row is None:
        return None
    if USE_POSTGRES:
        return row
    return dict(row)

def rows_to_dict(cur):
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return [dict(r) for r in cur.fetchall()]

def row_id(row):
    if row is None:
        return None
    return row[0] if USE_POSTGRES else row["id"]

def fetchone_dict(cur):
    row = cur.fetchone()
    if row is None:
        return None
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    return dict(row)

def log_error(source, message):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql("""
            INSERT INTO errors(source, message, created_at)
            VALUES (?, ?, ?)
        """), (source, str(message), now()))
        conn.commit()
        conn.close()
    except Exception:
        pass

def init_db():
    conn = get_db()
    cur = conn.cursor()
    pk = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    text = "TEXT"
    tables = [
        f"""CREATE TABLE IF NOT EXISTS users (
            id {pk},
            username {text} UNIQUE NOT NULL,
            password {text} NOT NULL,
            created_at {text},
            updated_at {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS customer_profiles (
            id {pk},
            name {text} UNIQUE NOT NULL,
            phone {text},
            address {text},
            notes {text},
            region {text},
            created_at {text},
            updated_at {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS inventory (
            id {pk},
            product_text {text} NOT NULL,
            product_code {text},
            qty INTEGER DEFAULT 0,
            location {text},
            customer_name {text},
            operator {text},
            source_text {text},
            created_at {text},
            updated_at {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS orders (
            id {pk},
            customer_name {text} NOT NULL,
            product_text {text} NOT NULL,
            product_code {text},
            qty INTEGER DEFAULT 0,
            status {text} DEFAULT 'pending',
            operator {text},
            created_at {text},
            updated_at {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS master_orders (
            id {pk},
            customer_name {text} NOT NULL,
            product_text {text} NOT NULL,
            product_code {text},
            qty INTEGER DEFAULT 0,
            operator {text},
            created_at {text},
            updated_at {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS shipping_records (
            id {pk},
            customer_name {text} NOT NULL,
            product_text {text} NOT NULL,
            product_code {text},
            qty INTEGER DEFAULT 0,
            operator {text},
            shipped_at {text},
            note {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS corrections (
            id {pk},
            wrong_text {text} UNIQUE NOT NULL,
            correct_text {text} NOT NULL,
            updated_at {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS image_hashes (
            id {pk},
            image_hash {text} UNIQUE NOT NULL,
            created_at {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS logs (
            id {pk},
            username {text},
            action {text},
            created_at {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS errors (
            id {pk},
            source {text},
            message {text},
            created_at {text}
        )""",
        f"""CREATE TABLE IF NOT EXISTS warehouse_cells (
            id {pk},
            zone {text} NOT NULL,
            column_index INTEGER NOT NULL,
            slot_type {text} NOT NULL,
            slot_number INTEGER NOT NULL,
            items_json {text},
            note {text},
            updated_at {text},
            UNIQUE(zone, column_index, slot_type, slot_number)
        )""",
    ]
    for t in tables:
        cur.execute(t)
    for zone in ("A", "B"):
        for col in range(1, 7):
            for slot_type in ("front", "back"):
                for num in range(1, 11):
                    if USE_POSTGRES:
                        cur.execute("""
                            INSERT INTO warehouse_cells(zone, column_index, slot_type, slot_number, items_json, note, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (zone, column_index, slot_type, slot_number) DO NOTHING
                        """, (zone, col, slot_type, num, "[]", "", now()))
                    else:
                        cur.execute("""
                            INSERT OR IGNORE INTO warehouse_cells(zone, column_index, slot_type, slot_number, items_json, note, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (zone, col, slot_type, num, "[]", "", now()))
    conn.commit()
    conn.close()

def get_user(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM users WHERE username = ?"), (username,))
    row = fetchone_dict(cur)
    conn.close()
    return row

def create_user(username, password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        INSERT INTO users(username, password, created_at, updated_at)
        VALUES (?, ?, ?, ?)
    """), (username, password, now(), now()))
    conn.commit()
    conn.close()

def update_password(username, new_password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        UPDATE users SET password = ?, updated_at = ?
        WHERE username = ?
    """), (new_password, now(), username))
    conn.commit()
    conn.close()

def log_action(username, action):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        INSERT INTO logs(username, action, created_at)
        VALUES (?, ?, ?)
    """), (username, action, now()))
    conn.commit()
    conn.close()

def image_hash_exists(image_hash):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT id FROM image_hashes WHERE image_hash = ?"), (image_hash,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def save_image_hash(image_hash):
    conn = get_db()
    cur = conn.cursor()
    try:
        if USE_POSTGRES:
            cur.execute("""
                INSERT INTO image_hashes(image_hash, created_at)
                VALUES (%s, %s)
                ON CONFLICT (image_hash) DO NOTHING
            """, (image_hash, now()))
        else:
            cur.execute("""
                INSERT OR IGNORE INTO image_hashes(image_hash, created_at)
                VALUES (?, ?)
            """, (image_hash, now()))
        conn.commit()
    except Exception as e:
        conn.rollback()
        log_error("save_image_hash", e)
    conn.close()

def save_correction(wrong, correct):
    conn = get_db()
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("""
            INSERT INTO corrections(wrong_text, correct_text, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (wrong_text) DO UPDATE SET correct_text = EXCLUDED.correct_text, updated_at = EXCLUDED.updated_at
        """, (wrong, correct, now()))
    else:
        cur.execute("""
            INSERT INTO corrections(wrong_text, correct_text, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(wrong_text) DO UPDATE SET correct_text=excluded.correct_text, updated_at=excluded.updated_at
        """, (wrong, correct, now()))
    conn.commit()
    conn.close()

def get_corrections():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT wrong_text, correct_text FROM corrections"))
    rows = rows_to_dict(cur)
    conn.close()
    return {r["wrong_text"]: r["correct_text"] for r in rows}

def upsert_customer(name, phone="", address="", notes="", region="北區"):
    conn = get_db()
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("""
            INSERT INTO customer_profiles(name, phone, address, notes, region, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(name) DO UPDATE SET phone=EXCLUDED.phone, address=EXCLUDED.address, notes=EXCLUDED.notes, region=EXCLUDED.region, updated_at=EXCLUDED.updated_at
        """, (name, phone, address, notes, region, now(), now()))
    else:
        cur.execute("""
            INSERT INTO customer_profiles(name, phone, address, notes, region, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET phone=excluded.phone, address=excluded.address, notes=excluded.notes, region=excluded.region, updated_at=excluded.updated_at
        """, (name, phone, address, notes, region, now(), now()))
    conn.commit()
    conn.close()

def get_customers():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM customer_profiles ORDER BY region, name"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def get_customer(name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM customer_profiles WHERE name = ?"), (name,))
    row = fetchone_dict(cur)
    conn.close()
    return row

def save_inventory_item(product_text, product_code, qty, location="", customer_name="", operator="", source_text=""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        SELECT id, qty FROM inventory
        WHERE product_text = ? AND COALESCE(location, '') = COALESCE(?, '')
    """), (product_text, location))
    row = cur.fetchone()
    if row:
        rid = row[0] if USE_POSTGRES else row["id"]
        cur.execute(sql("""
            UPDATE inventory
            SET qty = qty + ?, product_code = ?, customer_name = ?, operator = ?, source_text = ?, updated_at = ?
            WHERE id = ?
        """), (qty, product_code, customer_name, operator, source_text, now(), rid))
    else:
        cur.execute(sql("""
            INSERT INTO inventory(product_text, product_code, qty, location, customer_name, operator, source_text, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """), (product_text, product_code, qty, location, customer_name, operator, source_text, now(), now()))
    conn.commit()
    conn.close()

def list_inventory():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM inventory ORDER BY updated_at DESC, id DESC"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def save_order(customer_name, items, operator):
    conn = get_db()
    cur = conn.cursor()
    for item in items:
        cur.execute(sql("""
            INSERT INTO orders(customer_name, product_text, product_code, qty, status, operator, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
        """), (customer_name, item["product_text"], item.get("product_code", ""), int(item["qty"]), operator, now(), now()))
    conn.commit()
    conn.close()

def save_master_order(customer_name, items, operator):
    conn = get_db()
    cur = conn.cursor()
    for item in items:
        cur.execute(sql("""
            SELECT id FROM master_orders WHERE customer_name = ? AND product_text = ?
        """), (customer_name, item["product_text"]))
        row = cur.fetchone()
        if row:
            rid = row[0] if USE_POSTGRES else row["id"]
            cur.execute(sql("""
                UPDATE master_orders SET qty = qty + ?, product_code = ?, operator = ?, updated_at = ?
                WHERE id = ?
            """), (int(item["qty"]), item.get("product_code", ""), operator, now(), rid))
        else:
            cur.execute(sql("""
                INSERT INTO master_orders(customer_name, product_text, product_code, qty, operator, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """), (customer_name, item["product_text"], item.get("product_code", ""), int(item["qty"]), operator, now(), now()))
    conn.commit()
    conn.close()

def get_orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM orders ORDER BY id DESC"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def get_master_orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM master_orders ORDER BY id DESC"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def _deduct_from_table(cur, table, customer_name, product_text, qty_needed):
    cur.execute(sql(f"""
        SELECT id, qty
        FROM {table}
        WHERE customer_name = ? AND product_text = ? AND qty > 0
        ORDER BY id ASC
    """), (customer_name, product_text))
    rows = cur.fetchall()
    total = 0
    for row in rows:
        total += row[1] if USE_POSTGRES else row["qty"]
    if total < qty_needed:
        return False, []
    remain = qty_needed
    used = []
    for row in rows:
        rid = row[0] if USE_POSTGRES else row["id"]
        stock = row[1] if USE_POSTGRES else row["qty"]
        use_qty = min(stock, remain)
        cur.execute(sql(f"""
            UPDATE {table}
            SET qty = qty - ?, updated_at = ?
            WHERE id = ?
        """), (use_qty, now(), rid))
        used.append({"id": rid, "qty": use_qty})
        remain -= use_qty
        if remain <= 0:
            break
    return True, used

def _deduct_from_inventory(cur, product_text, qty_needed):
    cur.execute(sql("""
        SELECT id, qty
        FROM inventory
        WHERE product_text = ? AND qty > 0
        ORDER BY qty DESC, id ASC
    """), (product_text,))
    rows = cur.fetchall()
    total = sum((r[1] if USE_POSTGRES else r["qty"]) for r in rows)
    if total < qty_needed:
        return False, []
    remain = qty_needed
    used = []
    for row in rows:
        rid = row[0] if USE_POSTGRES else row["id"]
        stock = row[1] if USE_POSTGRES else row["qty"]
        use_qty = min(stock, remain)
        cur.execute(sql("""
            UPDATE inventory SET qty = qty - ?, updated_at = ? WHERE id = ?
        """), (use_qty, now(), rid))
        used.append({"id": rid, "qty": use_qty})
        remain -= use_qty
        if remain <= 0:
            break
    return True, used

def ship_order(customer_name, items, operator):
    conn = get_db()
    cur = conn.cursor()
    try:
        breakdown = []
        for item in items:
            product_text = item["product_text"]
            qty_needed = int(item["qty"])

            ok1, used_master = _deduct_from_table(cur, "master_orders", customer_name, product_text, qty_needed)
            if not ok1:
                conn.rollback()
                return {"success": False, "error": f"{product_text} 總單庫存不足"}

            ok2, used_order = _deduct_from_table(cur, "orders", customer_name, product_text, qty_needed)
            if not ok2:
                conn.rollback()
                return {"success": False, "error": f"{product_text} 訂單庫存不足"}

            ok3, used_inv = _deduct_from_inventory(cur, product_text, qty_needed)
            if not ok3:
                conn.rollback()
                return {"success": False, "error": f"{product_text} 庫存不足"}

            cur.execute(sql("""
                INSERT INTO shipping_records(customer_name, product_text, product_code, qty, operator, shipped_at, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """), (customer_name, product_text, item.get("product_code", ""), qty_needed, operator, now(), "已出貨"))

            breakdown.append({
                "product_text": product_text,
                "qty": qty_needed,
                "master_deduct": qty_needed,
                "order_deduct": qty_needed,
                "inventory_deduct": qty_needed
            })
        conn.commit()
        return {"success": True, "breakdown": breakdown}
    except Exception as e:
        conn.rollback()
        log_error("ship_order", e)
        return {"success": False, "error": "出貨失敗"}
    finally:
        conn.close()

def get_shipping_records(start_date=None, end_date=None):
    conn = get_db()
    cur = conn.cursor()
    q = "SELECT * FROM shipping_records WHERE 1=1"
    params = []
    if start_date:
        q += " AND date(shipped_at) >= date(?)"
        params.append(start_date)
    if end_date:
        q += " AND date(shipped_at) <= date(?)"
        params.append(end_date)
    q += " ORDER BY id DESC"
    cur.execute(sql(q), tuple(params))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def warehouse_get_cells():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM warehouse_cells ORDER BY zone, column_index, slot_type, slot_number"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def warehouse_get_cell(zone, column_index, slot_type, slot_number):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        SELECT * FROM warehouse_cells
        WHERE zone = ? AND column_index = ? AND slot_type = ? AND slot_number = ?
    """), (zone, column_index, slot_type, slot_number))
    row = fetchone_dict(cur)
    conn.close()
    return row

def warehouse_save_cell(zone, column_index, slot_type, slot_number, items, note=""):
    conn = get_db()
    cur = conn.cursor()
    items_json = json.dumps(items, ensure_ascii=False)
    cur.execute(sql("""
        UPDATE warehouse_cells
        SET items_json = ?, note = ?, updated_at = ?
        WHERE zone = ? AND column_index = ? AND slot_type = ? AND slot_number = ?
    """), (items_json, note, now(), zone, column_index, slot_type, slot_number))
    conn.commit()
    conn.close()

def warehouse_move_item(from_key, to_key, product_text, qty):
    conn = get_db()
    cur = conn.cursor()
    try:
        def _load(key):
            zone, column_index, slot_type, slot_number = key
            cur.execute(sql("""
                SELECT * FROM warehouse_cells
                WHERE zone = ? AND column_index = ? AND slot_type = ? AND slot_number = ?
            """), (zone, column_index, slot_type, slot_number))
            return fetchone_dict(cur)
        src = _load(from_key)
        dst = _load(to_key)
        src_items = json.loads(src["items_json"] or "[]")
        dst_items = json.loads(dst["items_json"] or "[]")
        moved = []
        remain = qty
        new_src = []
        for it in src_items:
            if it.get("product_text") == product_text and remain > 0:
                take = min(int(it.get("qty", 0)), remain)
                remain -= take
                moved.append({**it, "qty": take})
                leftover = int(it.get("qty", 0)) - take
                if leftover > 0:
                    new_src.append({**it, "qty": leftover})
            else:
                new_src.append(it)
        if remain > 0:
            return {"success": False, "error": "來源格位數量不足"}
        dst_items.extend(moved)
        cur.execute(sql("""
            UPDATE warehouse_cells SET items_json = ?, updated_at = ?
            WHERE zone = ? AND column_index = ? AND slot_type = ? AND slot_number = ?
        """), (json.dumps(new_src, ensure_ascii=False), now(), *from_key))
        cur.execute(sql("""
            UPDATE warehouse_cells SET items_json = ?, updated_at = ?
            WHERE zone = ? AND column_index = ? AND slot_type = ? AND slot_number = ?
        """), (json.dumps(dst_items, ensure_ascii=False), now(), *to_key))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        log_error("warehouse_move_item", e)
        return {"success": False, "error": "拖曳失敗"}
    finally:
        conn.close()

def inventory_placements():
    cells = warehouse_get_cells()
    placement = {}
    for cell in cells:
        try:
            items = json.loads(cell.get("items_json") or "[]")
        except Exception:
            items = []
        for it in items:
            key = it.get("product_text") or it.get("product") or ""
            placement[key] = placement.get(key, 0) + int(it.get("qty", 0))
    return placement

def inventory_summary():
    rows = list_inventory()
    placement = inventory_placements()
    result = []
    for r in rows:
        placed = placement.get(r["product_text"], 0)
        qty = int(r.get("qty", 0))
        result.append({
            **r,
            "placed_qty": placed,
            "unplaced_qty": max(0, qty - placed),
            "needs_red": max(0, qty - placed) > 0
        })
    return result

def warehouse_summary():
    cells = warehouse_get_cells()
    zones = {"A": {}, "B": {}}
    for cell in cells:
        zone = cell["zone"]
        col = int(cell["column_index"])
        slot_type = cell["slot_type"]
        num = int(cell["slot_number"])
        zones.setdefault(zone, {}).setdefault(col, {}).setdefault(slot_type, {})[num] = cell
    return zones

def list_backups():
    import os
    files = []
    backup_dir = "backups"
    if not os.path.isdir(backup_dir):
        return {"success": True, "files": []}
    for filename in os.listdir(backup_dir):
        path = os.path.join(backup_dir, filename)
        if os.path.isfile(path):
            files.append({
                "filename": filename,
                "size": os.path.getsize(path),
                "created_at": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
            })
    files.sort(key=lambda x: x["created_at"], reverse=True)
    return {"success": True, "files": files}

def get_activity_logs(limit=100, today_only=False, since=None):
    conn = get_db()
    cur = conn.cursor()
    q = "SELECT * FROM logs WHERE 1=1"
    params = []
    if today_only:
        q += " AND substr(created_at,1,10) = ?"
        params.append(now()[:10])
    if since:
        q += " AND created_at > ?"
        params.append(since)
    q += " ORDER BY id DESC"
    if limit:
        q += " LIMIT ?"
        params.append(int(limit))
    cur.execute(sql(q), tuple(params))
    rows = rows_to_dict(cur)
    conn.close()
    return rows


def get_today_error_count():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT COUNT(*) AS cnt FROM errors WHERE substr(created_at,1,10) = ?"), (now()[:10],))
    row = fetchone_dict(cur)
    conn.close()
    return int((row or {}).get('cnt', 0))


def get_today_shipping_qty():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT COALESCE(SUM(qty),0) AS total FROM shipping_records WHERE substr(shipped_at,1,10) = ?"), (now()[:10],))
    row = fetchone_dict(cur)
    conn.close()
    return int((row or {}).get('total', 0))

