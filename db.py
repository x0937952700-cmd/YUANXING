import os
import sqlite3
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///warehouse.db")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    import psycopg2


# =====================================
# 共用
# =====================================
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


def row_to_dict(cur, row):
    if row is None:
        return None
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    return dict(row)


def rows_to_dict(cur):
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return [dict(r) for r in cur.fetchall()]


def row_id(row):
    return row[0] if USE_POSTGRES else row["id"]


# =====================================
# 初始化
# =====================================
def init_db():
    conn = get_db()
    cur = conn.cursor()

    pk = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"

    tables = [
        f"""CREATE TABLE IF NOT EXISTS users (
            id {pk},
            username TEXT UNIQUE,
            password TEXT,
            created_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS inventory (
            id {pk},
            product TEXT,
            quantity INTEGER DEFAULT 0,
            location TEXT,
            operator TEXT,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS orders (
            id {pk},
            customer TEXT,
            product TEXT,
            qty INTEGER,
            status TEXT,
            operator TEXT,
            created_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS master_orders (
            id {pk},
            customer TEXT,
            product TEXT,
            qty INTEGER,
            operator TEXT,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS shipping_records (
            id {pk},
            customer TEXT,
            product TEXT,
            qty INTEGER,
            operator TEXT,
            shipped_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS corrections (
            id {pk},
            wrong_text TEXT UNIQUE,
            correct_text TEXT,
            updated_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS image_hashes (
            id {pk},
            image_hash TEXT UNIQUE,
            created_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS logs (
            id {pk},
            username TEXT,
            action TEXT,
            created_at TEXT
        )""",
        f"""CREATE TABLE IF NOT EXISTS errors (
            id {pk},
            source TEXT,
            message TEXT,
            created_at TEXT
        )"""
    ]

    for table in tables:
        cur.execute(table)

    conn.commit()
    conn.close()


# =====================================
# 使用者
# =====================================
def get_user(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM users WHERE username=?"), (username,))
    row = cur.fetchone()
    result = row_to_dict(cur, row)
    conn.close()
    return result


def create_user(username, password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        INSERT INTO users(username,password,created_at)
        VALUES(?,?,?)
    """), (username, password, now()))
    conn.commit()
    conn.close()


# =====================================
# 紀錄
# =====================================
def log_action(username, action):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        INSERT INTO logs(username,action,created_at)
        VALUES(?,?,?)
    """), (username, action, now()))
    conn.commit()
    conn.close()


def log_error(source, message):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql("""
            INSERT INTO errors(source,message,created_at)
            VALUES(?,?,?)
        """), (source, str(message), now()))
        conn.commit()
        conn.close()
    except Exception:
        pass


# =====================================
# 圖片 hash
# =====================================
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
            cur.execute("""
                INSERT INTO image_hashes(image_hash,created_at)
                VALUES(%s,%s)
                ON CONFLICT (image_hash) DO NOTHING
            """, (image_hash, now()))
        else:
            cur.execute("""
                INSERT OR IGNORE INTO image_hashes(image_hash,created_at)
                VALUES(?,?)
            """, (image_hash, now()))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


# =====================================
# OCR 修正
# =====================================
def save_correction(wrong, correct):
    conn = get_db()
    cur = conn.cursor()

    cur.execute(sql("DELETE FROM corrections WHERE wrong_text=?"), (wrong,))
    cur.execute(sql("""
        INSERT INTO corrections(wrong_text,correct_text,updated_at)
        VALUES(?,?,?)
    """), (wrong, correct, now()))

    conn.commit()
    conn.close()


def get_corrections_map():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT wrong_text, correct_text FROM corrections"))
    rows = cur.fetchall()
    if USE_POSTGRES:
        result = {r[0]: r[1] for r in rows}
    else:
        result = {r["wrong_text"]: r["correct_text"] for r in rows}
    conn.close()
    return result


# =====================================
# 庫存
# =====================================
def save_inventory(item):
    product = str(item["product"]).strip()
    qty = int(item["quantity"])
    location = str(item.get("location", "")).strip()
    operator = str(item.get("operator", "")).strip()

    conn = get_db()
    cur = conn.cursor()

    cur.execute(sql("""
        SELECT id FROM inventory
        WHERE product=? AND location=?
    """), (product, location))
    row = cur.fetchone()

    if row:
        cur.execute(sql("""
            UPDATE inventory
            SET quantity=quantity+?,
                operator=?,
                updated_at=?
            WHERE id=?
        """), (qty, operator, now(), row_id(row)))
    else:
        cur.execute(sql("""
            INSERT INTO inventory(product,quantity,location,operator,updated_at)
            VALUES(?,?,?,?,?)
        """), (product, qty, location, operator, now()))

    conn.commit()
    conn.close()


def get_inventory_snapshot():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        SELECT * FROM inventory
        ORDER BY product ASC, location ASC, id ASC
    """))
    rows = rows_to_dict(cur)
    conn.close()
    return rows


# =====================================
# 訂單
# =====================================
def save_order(customer, items, operator):
    conn = get_db()
    cur = conn.cursor()

    for item in items:
        product = str(item["product"]).strip()
        qty = int(item["quantity"])
        cur.execute(sql("""
            INSERT INTO orders(customer,product,qty,status,operator,created_at)
            VALUES(?,?,?,?,?,?)
        """), (customer, product, qty, "pending", operator, now()))

    conn.commit()
    conn.close()


def get_orders_snapshot():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        SELECT * FROM orders
        ORDER BY id DESC
    """))
    rows = rows_to_dict(cur)
    conn.close()
    return rows


# =====================================
# 總單
# =====================================
def save_master_order(customer, items, operator):
    conn = get_db()
    cur = conn.cursor()

    for item in items:
        product = str(item["product"]).strip()
        qty = int(item["quantity"])

        cur.execute(sql("""
            SELECT id FROM master_orders
            WHERE customer=? AND product=?
        """), (customer, product))
        row = cur.fetchone()

        if row:
            cur.execute(sql("""
                UPDATE master_orders
                SET qty=qty+?, operator=?, updated_at=?
                WHERE id=?
            """), (qty, operator, now(), row_id(row)))
        else:
            cur.execute(sql("""
                INSERT INTO master_orders(customer,product,qty,operator,updated_at)
                VALUES(?,?,?,?,?)
            """), (customer, product, qty, operator, now()))

    conn.commit()
    conn.close()


def get_master_orders_snapshot():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        SELECT * FROM master_orders
        ORDER BY updated_at DESC, id DESC
    """))
    rows = rows_to_dict(cur)
    conn.close()
    return rows


# =====================================
# 出貨
# =====================================
def _deduct_master_order(cur, customer, product, qty_needed):
    cur.execute(sql("""
        SELECT id, qty FROM master_orders
        WHERE customer=? AND product=?
        ORDER BY id ASC
    """), (customer, product))
    rows = cur.fetchall()

    if USE_POSTGRES:
        total = sum(r[1] for r in rows)
    else:
        total = sum(r["qty"] for r in rows)

    if total < qty_needed:
        return False, "總單不足"

    remain = qty_needed
    for row in rows:
        rid = row[0] if USE_POSTGRES else row["id"]
        row_qty = row[1] if USE_POSTGRES else row["qty"]
        use_qty = min(row_qty, remain)
        new_qty = row_qty - use_qty

        if new_qty > 0:
            cur.execute(sql("""
                UPDATE master_orders
                SET qty=?, updated_at=?
                WHERE id=?
            """), (new_qty, now(), rid))
        else:
            cur.execute(sql("DELETE FROM master_orders WHERE id=?"), (rid,))

        remain -= use_qty
        if remain <= 0:
            break

    return True, ""


def _deduct_orders(cur, customer, product, qty_needed):
    cur.execute(sql("""
        SELECT id, qty FROM orders
        WHERE customer=? AND product=? AND status='pending'
        ORDER BY created_at ASC, id ASC
    """), (customer, product))
    rows = cur.fetchall()

    if USE_POSTGRES:
        total = sum(r[1] for r in rows)
    else:
        total = sum(r["qty"] for r in rows)

    if total < qty_needed:
        return False, "訂單不足"

    remain = qty_needed
    for row in rows:
        rid = row[0] if USE_POSTGRES else row["id"]
        row_qty = row[1] if USE_POSTGRES else row["qty"]
        use_qty = min(row_qty, remain)
        new_qty = row_qty - use_qty

        if new_qty > 0:
            cur.execute(sql("""
                UPDATE orders
                SET qty=?, updated_at=?
                WHERE id=?
            """), (new_qty, now(), rid))
        else:
            cur.execute(sql("DELETE FROM orders WHERE id=?"), (rid,))

        remain -= use_qty
        if remain <= 0:
            break

    return True, ""


def _deduct_inventory(cur, product, qty_needed):
    cur.execute(sql("""
        SELECT id, quantity, location FROM inventory
        WHERE product=? AND quantity>0
        ORDER BY quantity DESC, id ASC
    """), (product,))
    rows = cur.fetchall()

    if USE_POSTGRES:
        total = sum(r[1] for r in rows)
    else:
        total = sum(r["quantity"] for r in rows)

    if total < qty_needed:
        return False, "庫存不足"

    remain = qty_needed
    for row in rows:
        rid = row[0] if USE_POSTGRES else row["id"]
        row_qty = row[1] if USE_POSTGRES else row["quantity"]
        use_qty = min(row_qty, remain)
        new_qty = row_qty - use_qty

        cur.execute(sql("""
            UPDATE inventory
            SET quantity=?, updated_at=?
            WHERE id=?
        """), (new_qty, now(), rid))

        remain -= use_qty
        if remain <= 0:
            break

    return True, ""


def ship_order(customer, items, operator):
    conn = get_db()
    cur = conn.cursor()

    try:
        for item in items:
            product = str(item["product"]).strip()
            qty_needed = int(item["quantity"])

            ok, err = _deduct_master_order(cur, customer, product, qty_needed)
            if not ok:
                conn.rollback()
                return {"success": False, "error": f"{product} {err}"}

            ok, err = _deduct_orders(cur, customer, product, qty_needed)
            if not ok:
                conn.rollback()
                return {"success": False, "error": f"{product} {err}"}

            ok, err = _deduct_inventory(cur, product, qty_needed)
            if not ok:
                conn.rollback()
                return {"success": False, "error": f"{product} {err}"}

            cur.execute(sql("""
                INSERT INTO shipping_records(customer,product,qty,operator,shipped_at)
                VALUES(?,?,?,?,?)
            """), (customer, product, qty_needed, operator, now()))

        conn.commit()
        return {"success": True}

    except Exception as e:
        conn.rollback()
        log_error("ship_order", str(e))
        return {"success": False, "error": "出貨失敗"}

    finally:
        conn.close()


def get_shipping_records():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        SELECT * FROM shipping_records
        ORDER BY id DESC
    """))
    rows = rows_to_dict(cur)
    conn.close()
    return rows


# =====================================
# 操作紀錄
# =====================================
def get_logs_snapshot():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("""
        SELECT * FROM logs
        ORDER BY id DESC
    """))
    rows = rows_to_dict(cur)
    conn.close()
    return rows


# =====================================
# 倉庫定位
# =====================================
def find_multiple_locations(items):
    conn = get_db()
    cur = conn.cursor()
    result = []

    for item in items:
        if isinstance(item, dict):
            product = str(item.get("product", "")).strip()
        else:
            product = str(item).strip()

        if not product:
            continue

        cur.execute(sql("""
            SELECT location, quantity, product
            FROM inventory
            WHERE product=? AND quantity>0
            ORDER BY quantity DESC, location ASC
        """), (product,))
        rows = rows_to_dict(cur)

        for row in rows:
            result.append({
                "product": product,
                "location": row.get("location", ""),
                "quantity": row.get("quantity", 0)
            })

    conn.close()
    return result
