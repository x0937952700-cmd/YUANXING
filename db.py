
import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///warehouse.db")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    import psycopg2

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sql(q):
    return q.replace("?", "%s") if USE_POSTGRES else q

def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    db_path = DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def rows_to_dict(cur):
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    return [dict(r) for r in cur.fetchall()]

def row_id(row):
    return row[0] if USE_POSTGRES else row["id"]

def scalar_count(cur):
    row = cur.fetchone()
    return row[0] if USE_POSTGRES else row["c"]

def init_db():
    conn = get_db()
    cur = conn.cursor()
    pk = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    stmts = [
        f"""CREATE TABLE IF NOT EXISTS users(
            id {pk},
            username TEXT UNIQUE,
            password TEXT,
            created_at TEXT,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS inventory(
            id {pk},
            product TEXT,
            quantity INTEGER DEFAULT 0,
            location TEXT,
            operator TEXT,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS orders(
            id {pk},
            customer TEXT,
            product TEXT,
            qty INTEGER,
            status TEXT,
            operator TEXT,
            created_at TEXT,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS master_orders(
            id {pk},
            customer TEXT,
            product TEXT,
            qty INTEGER,
            operator TEXT,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS shipping_records(
            id {pk},
            customer TEXT,
            product TEXT,
            qty INTEGER,
            operator TEXT,
            source_type TEXT,
            note TEXT,
            shipped_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS corrections(
            id {pk},
            wrong_text TEXT UNIQUE,
            correct_text TEXT,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS image_hashes(
            id {pk},
            image_hash TEXT UNIQUE,
            created_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS logs(
            id {pk},
            username TEXT,
            action TEXT,
            created_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS errors(
            id {pk},
            source TEXT,
            message TEXT,
            created_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS customers(
            id {pk},
            name TEXT UNIQUE,
            phone TEXT,
            address TEXT,
            notes TEXT,
            region TEXT,
            sort_order INTEGER DEFAULT 0,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS warehouse_slots(
            id {pk},
            slot_name TEXT UNIQUE,
            customer TEXT,
            product TEXT,
            quantity INTEGER DEFAULT 0,
            note TEXT,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS settings(
            id {pk},
            key TEXT UNIQUE,
            value TEXT,
            updated_at TEXT
        )""",
    ]
    for s in stmts:
        cur.execute(s)
    conn.commit()
    conn.close()

def get_user(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM users WHERE username=?"), (username,))
    row = cur.fetchone()
    conn.close()
    return row

def create_user(username, password):
    conn = get_db()
    cur = conn.cursor()
    pw = generate_password_hash(password)
    cur.execute(sql("INSERT INTO users(username,password,created_at,updated_at) VALUES(?,?,?,?)"), (username, pw, now(), now()))
    conn.commit()
    conn.close()

def update_user_password(username, password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("UPDATE users SET password=?, updated_at=? WHERE username=?"), (generate_password_hash(password), now(), username))
    conn.commit()
    conn.close()

def log_action(username, action):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("INSERT INTO logs(username,action,created_at) VALUES(?,?,?)"), (username, action, now()))
    conn.commit()
    conn.close()

def log_error(source, message):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql("INSERT INTO errors(source,message,created_at) VALUES(?,?,?)"), (source, str(message), now()))
        conn.commit()
        conn.close()
    except Exception:
        pass

def image_hash_exists(image_hash):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT id FROM image_hashes WHERE image_hash=?"), (image_hash,))
    row = cur.fetchone()
    conn.close()
    return row is not None

def save_image_hash(image_hash):
    conn = get_db()
    cur = conn.cursor()
    try:
        if USE_POSTGRES:
            cur.execute("INSERT INTO image_hashes(image_hash,created_at) VALUES(%s,%s) ON CONFLICT (image_hash) DO NOTHING", (image_hash, now()))
        else:
            cur.execute("INSERT OR IGNORE INTO image_hashes(image_hash,created_at) VALUES(?,?)", (image_hash, now()))
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()

def save_correction(wrong, correct):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("DELETE FROM corrections WHERE wrong_text=?"), (wrong,))
    cur.execute(sql("INSERT INTO corrections(wrong_text,correct_text,updated_at) VALUES(?,?,?)"), (wrong, correct, now()))
    conn.commit()
    conn.close()

def get_corrections():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT wrong_text, correct_text FROM corrections"))
    rows = rows_to_dict(cur)
    conn.close()
    return {r["wrong_text"]: r["correct_text"] for r in rows}

def get_known_products():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT DISTINCT product FROM inventory WHERE product IS NOT NULL AND product<>''"))
    rows = rows_to_dict(cur)
    conn.close()
    return [r["product"] for r in rows if r.get("product")]

def save_inventory(item):
    conn = get_db()
    cur = conn.cursor()
    product = item["product"]
    qty = int(item["quantity"])
    location = item.get("location", "")
    operator = item.get("operator", "")
    cur.execute(sql("SELECT id FROM inventory WHERE product=? AND location=?"), (product, location))
    row = cur.fetchone()
    if row:
        cur.execute(sql("UPDATE inventory SET quantity=quantity+?, operator=?, updated_at=? WHERE id=?"), (qty, operator, now(), row_id(row)))
    else:
        cur.execute(sql("INSERT INTO inventory(product,quantity,location,operator,updated_at) VALUES(?,?,?,?,?)"), (product, qty, location, operator, now()))
    conn.commit()
    conn.close()

def save_order(customer, items, operator):
    conn = get_db()
    cur = conn.cursor()
    for item in items:
        cur.execute(sql("INSERT INTO orders(customer,product,qty,status,operator,created_at,updated_at) VALUES(?,?,?,?,?,?,?)"), (customer, item["product"], int(item["quantity"]), "pending", operator, now(), now()))
    conn.commit()
    conn.close()

def save_master_order(customer, items, operator):
    conn = get_db()
    cur = conn.cursor()
    for item in items:
        product = item["product"]
        qty = int(item["quantity"])
        cur.execute(sql("SELECT id FROM master_orders WHERE customer=? AND product=?"), (customer, product))
        row = cur.fetchone()
        if row:
            cur.execute(sql("UPDATE master_orders SET qty=qty+?, operator=?, updated_at=? WHERE id=?"), (qty, operator, now(), row_id(row)))
        else:
            cur.execute(sql("INSERT INTO master_orders(customer,product,qty,operator,updated_at) VALUES(?,?,?,?,?)"), (customer, product, qty, operator, now()))
    conn.commit()
    conn.close()

def _deduct_table(cur, table, customer, product, qty_needed=None):
    if table == "inventory":
        cur.execute(sql("SELECT id, quantity, location FROM inventory WHERE product=? AND quantity>0 ORDER BY quantity DESC, id ASC"), (product,))
        rows = cur.fetchall()
        total = sum((r[1] if USE_POSTGRES else r["quantity"]) for r in rows)
        if total < qty_needed:
            raise ValueError(f"{product} 庫存不足")
        deducted = 0
        locations = []
        for row in rows:
            if deducted >= qty_needed:
                break
            rid = row[0] if USE_POSTGRES else row["id"]
            qty = row[1] if USE_POSTGRES else row["quantity"]
            loc = row[2] if USE_POSTGRES else row["location"]
            use_qty = min(qty, qty_needed - deducted)
            cur.execute(sql("UPDATE inventory SET quantity=quantity-?, updated_at=? WHERE id=?"), (use_qty, now(), rid))
            locations.append({"location": loc, "quantity": use_qty})
            deducted += use_qty
        return deducted, locations

    if table == "master_orders":
        cur.execute(sql("SELECT id, qty FROM master_orders WHERE customer=? AND product=? ORDER BY id ASC"), (customer, product))
    else:
        cur.execute(sql("SELECT id, qty FROM orders WHERE customer=? AND product=? AND status='pending' ORDER BY id ASC"), (customer, product))

    rows = cur.fetchall()
    deducted = 0
    for row in rows:
        if deducted >= qty_needed:
            break
        rid = row[0] if USE_POSTGRES else row["id"]
        qty = row[1] if USE_POSTGRES else row["qty"]
        use_qty = min(qty, qty_needed - deducted)
        if table == "master_orders":
            cur.execute(sql("UPDATE master_orders SET qty=qty-?, updated_at=? WHERE id=?"), (use_qty, now(), rid))
        else:
            cur.execute(sql("UPDATE orders SET qty=qty-?, updated_at=?, status=CASE WHEN qty-? <= 0 THEN 'done' ELSE status END WHERE id=?"), (use_qty, now(), use_qty, rid))
        deducted += use_qty
    return deducted, []

def ship_order(customer, items, operator):
    conn = get_db()
    cur = conn.cursor()
    try:
        breakdown = []
        for item in items:
            product = item["product"]
            qty_needed = int(item["quantity"])
            d_master, _ = _deduct_table(cur, "master_orders", customer, product, qty_needed)
            d_order, _ = _deduct_table(cur, "orders", customer, product, qty_needed)
            d_inv, locations = _deduct_table(cur, "inventory", customer, product, qty_needed)
            cur.execute(sql("INSERT INTO shipping_records(customer,product,qty,operator,source_type,note,shipped_at) VALUES(?,?,?,?,?,?,?)"), (
                customer, product, qty_needed, operator, "master+order+inventory",
                f"master:{d_master};order:{d_order};inventory:{d_inv}", now()
            ))
            breakdown.append({
                "customer": customer, "product": product, "qty": qty_needed,
                "deducted_master": d_master, "deducted_order": d_order,
                "deducted_inventory": d_inv, "inventory_locations": locations
            })
        conn.commit()
        return {"success": True, "breakdown": breakdown}
    except Exception as e:
        conn.rollback()
        log_error("ship_order", e)
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def get_shipping_records():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM shipping_records ORDER BY id DESC"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def find_multiple_locations(items):
    conn = get_db()
    cur = conn.cursor()
    result = []
    for item in items:
        product = item["product"] if isinstance(item, dict) else item
        cur.execute(sql("SELECT location, quantity FROM inventory WHERE product=? AND quantity>0 ORDER BY quantity DESC, id ASC"), (product,))
        rows = rows_to_dict(cur)
        for row in rows:
            result.append({"product": product, "location": row["location"], "quantity": row["quantity"]})
    conn.close()
    return result

def list_customers():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM customers ORDER BY region ASC, sort_order ASC, name ASC"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def get_customer(name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM customers WHERE name=?"), (name,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
    else:
        data = dict(row)
    conn.close()
    return data

def save_customer(data):
    conn = get_db()
    cur = conn.cursor()
    name = data["name"]
    cur.execute(sql("SELECT id FROM customers WHERE name=?"), (name,))
    row = cur.fetchone()
    if row:
        cur.execute(sql("UPDATE customers SET phone=?, address=?, notes=?, region=?, sort_order=?, updated_at=? WHERE name=?"), (
            data.get("phone",""), data.get("address",""), data.get("notes",""), data.get("region","北區"), int(data.get("sort_order") or 0), now(), name
        ))
    else:
        cur.execute(sql("INSERT INTO customers(name,phone,address,notes,region,sort_order,updated_at) VALUES(?,?,?,?,?,?,?)"), (
            name, data.get("phone",""), data.get("address",""), data.get("notes",""), data.get("region","北區"), int(data.get("sort_order") or 0), now()
        ))
    conn.commit()
    conn.close()
    return {**data, "updated_at": now()}

def seed_default_customers():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT COUNT(*) AS c FROM customers"))
    count = scalar_count(cur)
    conn.close()
    if count:
        return
    defaults = [
        ("保固","", "", "", "北區", 1),
        ("德馨","", "", "", "北區", 2),
        ("龍興","", "", "", "北區", 3),
        ("三美","", "", "", "中區", 1),
        ("揚舜","", "", "", "南區", 1),
        ("國翔","", "", "", "南區", 2),
    ]
    conn = get_db()
    cur = conn.cursor()
    for d in defaults:
        cur.execute(sql("INSERT INTO customers(name,phone,address,notes,region,sort_order,updated_at) VALUES(?,?,?,?,?,?,?)"), (*d, now()))
    conn.commit()
    conn.close()

def list_warehouse_slots():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM warehouse_slots ORDER BY id ASC"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def save_warehouse_slot(data):
    conn = get_db()
    cur = conn.cursor()
    slot_name = data["slot_name"]
    cur.execute(sql("SELECT id FROM warehouse_slots WHERE slot_name=?"), (slot_name,))
    row = cur.fetchone()
    if row:
        cur.execute(sql("UPDATE warehouse_slots SET customer=?, product=?, quantity=?, note=?, updated_at=? WHERE slot_name=?"), (
            data.get("customer",""), data.get("product",""), int(data.get("quantity") or 0), data.get("note",""), now(), slot_name
        ))
    else:
        cur.execute(sql("INSERT INTO warehouse_slots(slot_name,customer,product,quantity,note,updated_at) VALUES(?,?,?,?,?,?)"), (
            slot_name, data.get("customer",""), data.get("product",""), int(data.get("quantity") or 0), data.get("note",""), now()
        ))
    conn.commit()
    conn.close()
    return {**data, "updated_at": now()}

def delete_warehouse_slot(slot_name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("DELETE FROM warehouse_slots WHERE slot_name=?"), (slot_name,))
    conn.commit()
    conn.close()

def get_settings():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT key, value FROM settings ORDER BY key ASC"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows

def set_setting(key, value):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT id FROM settings WHERE key=?"), (key,))
    row = cur.fetchone()
    if row:
        cur.execute(sql("UPDATE settings SET value=?, updated_at=? WHERE key=?"), (value, now(), key))
    else:
        cur.execute(sql("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)"), (key, value, now()))
    conn.commit()
    conn.close()
