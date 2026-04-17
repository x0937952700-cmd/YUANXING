import os
import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///warehouse.db")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    import psycopg2


# =====================================
# 基本工具
# =====================================
def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sql(query: str) -> str:
    return query.replace("?", "%s") if USE_POSTGRES else query


def _sqlite_path() -> str:
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


# =====================================
# Schema migration helpers
# =====================================
def _table_columns(cur, table: str) -> set:
    if USE_POSTGRES:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        )
        return {r[0] for r in cur.fetchall()}

    cur.execute(f"PRAGMA table_info({table})")
    return {r[1] for r in cur.fetchall()}


def _ensure_column(cur, table: str, column: str, coltype: str):
    try:
        cols = _table_columns(cur, table)
        if column in cols:
            return
        if USE_POSTGRES:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        else:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
    except Exception as e:
        # 不讓舊 schema 直接炸掉部署
        try:
            log_error(f"migrate_{table}_{column}", str(e))
        except Exception:
            pass


def _dedupe_by_keys(cur, table: str, key_columns: Sequence[str]):
    """
    盡量把舊資料中重複 key 的資料清掉，避免後續建立 unique index / ON CONFLICT 失敗。
    """
    try:
        if USE_POSTGRES:
            # 保留最小 id，刪除其餘重複資料
            join_cond = " AND ".join([f"t.{c} = d.{c}" for c in key_columns])
            cur.execute(
                f"""
                DELETE FROM {table} t
                USING {table} d
                WHERE t.id > d.id
                  AND {join_cond}
                """
            )
        else:
            cols = ", ".join(key_columns)
            cur.execute(
                f"""
                DELETE FROM {table}
                WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                    FROM {table}
                    GROUP BY {cols}
                )
                """
            )
    except Exception as e:
        # 舊表若結構不完整或本來就沒有資料，不必中止
        try:
            log_error(f"dedupe_{table}", str(e))
        except Exception:
            pass


def _ensure_unique_index(cur, table: str, index_name: str, columns: Sequence[str]):
    try:
        cols_sql = ", ".join(columns)
        if USE_POSTGRES:
            cur.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} ({cols_sql})"
            )
        else:
            cur.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} ({cols_sql})"
            )
    except Exception as e:
        try:
            log_error(f"index_{index_name}", str(e))
        except Exception:
            pass


def _migrate_schema(cur):
    """
    把 legacy schema 補齊成新版本欄位，避免部署後因欄位不一致而掛掉。
    """
    needed = {
        "users": [("updated_at", "TEXT")],
        "customer_profiles": [
            ("phone", "TEXT"),
            ("address", "TEXT"),
            ("notes", "TEXT"),
            ("region", "TEXT"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
        ],
        "inventory": [
            ("product_code", "TEXT"),
            ("customer_name", "TEXT"),
            ("operator", "TEXT"),
            ("source_text", "TEXT"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
        ],
        "orders": [("product_code", "TEXT"), ("updated_at", "TEXT")],
        "master_orders": [("product_code", "TEXT"), ("updated_at", "TEXT")],
        "shipping_records": [("product_code", "TEXT"), ("note", "TEXT")],
        "corrections": [("updated_at", "TEXT")],
        "image_hashes": [("created_at", "TEXT")],
        "logs": [("created_at", "TEXT")],
        "errors": [("created_at", "TEXT")],
        "warehouse_cells": [
            ("zone", "TEXT"),
            ("column_index", "INTEGER"),
            ("slot_type", "TEXT"),
            ("slot_number", "INTEGER"),
            ("items_json", "TEXT"),
            ("note", "TEXT"),
            ("updated_at", "TEXT"),
        ],
    }

    for table, columns in needed.items():
        for column, coltype in columns:
            _ensure_column(cur, table, column, coltype)


def _ensure_legacy_safe_indexes(cur):
    """
    讓 ON CONFLICT 所需的唯一鍵在既有資料庫也能成立。
    """
    # 先去重，再補 unique index
    dedupe_jobs = [
        ("users", ["username"], "users_username_uq"),
        ("customer_profiles", ["name"], "customer_profiles_name_uq"),
        ("corrections", ["wrong_text"], "corrections_wrong_text_uq"),
        ("image_hashes", ["image_hash"], "image_hashes_image_hash_uq"),
        ("warehouse_cells", ["zone", "column_index", "slot_type", "slot_number"], "warehouse_cells_zone_col_type_num_uq"),
    ]

    for table, keys, index_name in dedupe_jobs:
        _dedupe_by_keys(cur, table, keys)
        _ensure_unique_index(cur, table, index_name, keys)


# =====================================
# 錯誤紀錄
# =====================================
def log_error(source, message):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            sql(
                """
                INSERT INTO errors(source, message, created_at)
                VALUES (?, ?, ?)
                """
            ),
            (source, str(message), now()),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# =====================================
# 初始化資料表
# =====================================
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
            updated_at {text}
        )""",
    ]

    for stmt in tables:
        cur.execute(stmt)

    # legacy schema 補欄位 / 補唯一鍵，避免 ON CONFLICT 失敗
    _migrate_schema(cur)
    _ensure_legacy_safe_indexes(cur)

    # 初始化倉庫格位：A/B 區，各 6 欄，前後各 1~10
    for zone in ("A", "B"):
        for col in range(1, 7):
            for slot_type in ("front", "back"):
                for num in range(1, 11):
                    if USE_POSTGRES:
                        cur.execute(
                            """
                            INSERT INTO warehouse_cells(
                                zone, column_index, slot_type, slot_number,
                                items_json, note, updated_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (zone, column_index, slot_type, slot_number) DO NOTHING
                            """,
                            (zone, col, slot_type, num, "[]", "", now()),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT OR IGNORE INTO warehouse_cells(
                                zone, column_index, slot_type, slot_number,
                                items_json, note, updated_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (zone, col, slot_type, num, "[]", "", now()),
                        )

    conn.commit()
    conn.close()


# =====================================
# 使用者
# =====================================
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
    cur.execute(
        sql(
            """
            INSERT INTO users(username, password, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """
        ),
        (username, password, now(), now()),
    )
    conn.commit()
    conn.close()


def update_password(username, new_password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        sql(
            """
            UPDATE users
            SET password = ?, updated_at = ?
            WHERE username = ?
            """
        ),
        (new_password, now(), username),
    )
    conn.commit()
    conn.close()


# =====================================
# 記錄
# =====================================
def log_action(username, action):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        sql(
            """
            INSERT INTO logs(username, action, created_at)
            VALUES (?, ?, ?)
            """
        ),
        (username, action, now()),
    )
    conn.commit()
    conn.close()


# =====================================
# 圖片 hash
# =====================================
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
            cur.execute(
                """
                INSERT INTO image_hashes(image_hash, created_at)
                VALUES (%s, %s)
                ON CONFLICT (image_hash) DO NOTHING
                """,
                (image_hash, now()),
            )
        else:
            cur.execute(
                """
                INSERT OR IGNORE INTO image_hashes(image_hash, created_at)
                VALUES (?, ?)
                """,
                (image_hash, now()),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        log_error("save_image_hash", e)
    finally:
        conn.close()


# =====================================
# OCR 修正
# =====================================
def save_correction(wrong, correct):
    conn = get_db()
    cur = conn.cursor()
    try:
        if USE_POSTGRES:
            cur.execute(
                """
                INSERT INTO corrections(wrong_text, correct_text, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (wrong_text)
                DO UPDATE SET
                    correct_text = EXCLUDED.correct_text,
                    updated_at = EXCLUDED.updated_at
                """,
                (wrong, correct, now()),
            )
        else:
            cur.execute(
                """
                INSERT INTO corrections(wrong_text, correct_text, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(wrong_text)
                DO UPDATE SET
                    correct_text = excluded.correct_text,
                    updated_at = excluded.updated_at
                """,
                (wrong, correct, now()),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        log_error("save_correction", e)
    finally:
        conn.close()


def get_corrections():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT wrong_text, correct_text FROM corrections"))
    rows = rows_to_dict(cur)
    conn.close()
    return {r["wrong_text"]: r["correct_text"] for r in rows}


# =====================================
# 客戶資料
# =====================================
def upsert_customer(name, phone="", address="", notes="", region="北區"):
    conn = get_db()
    cur = conn.cursor()
    try:
        if USE_POSTGRES:
            cur.execute(
                """
                INSERT INTO customer_profiles(name, phone, address, notes, region, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(name) DO UPDATE SET
                    phone = EXCLUDED.phone,
                    address = EXCLUDED.address,
                    notes = EXCLUDED.notes,
                    region = EXCLUDED.region,
                    updated_at = EXCLUDED.updated_at
                """,
                (name, phone, address, notes, region, now(), now()),
            )
        else:
            cur.execute(
                """
                INSERT INTO customer_profiles(name, phone, address, notes, region, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    phone = excluded.phone,
                    address = excluded.address,
                    notes = excluded.notes,
                    region = excluded.region,
                    updated_at = excluded.updated_at
                """,
                (name, phone, address, notes, region, now(), now()),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        log_error("upsert_customer", e)
    finally:
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


# =====================================
# 庫存
# =====================================
def save_inventory(item):
    """
    相容舊版 app.py：直接收 item dict。
    也可容許不同欄位名稱，例如 product / product_text, quantity / qty.
    """
    if not isinstance(item, dict):
        raise ValueError("save_inventory 需要 dict 類型資料")

    product_text = item.get("product_text") or item.get("product") or ""
    product_code = item.get("product_code") or ""
    qty = int(item.get("quantity", item.get("qty", 0)) or 0)
    location = item.get("location", "") or ""
    customer_name = item.get("customer_name", "") or item.get("customer", "") or ""
    operator = item.get("operator", "") or ""
    source_text = item.get("source_text", "") or item.get("raw_text", "") or ""

    save_inventory_item(
        product_text=product_text,
        product_code=product_code,
        qty=qty,
        location=location,
        customer_name=customer_name,
        operator=operator,
        source_text=source_text,
    )


def save_inventory_item(
    product_text: str,
    product_code: str,
    qty: int,
    location: str = "",
    customer_name: str = "",
    operator: str = "",
    source_text: str = "",
):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            sql(
                """
                SELECT id, qty
                FROM inventory
                WHERE product_text = ? AND COALESCE(location, '') = COALESCE(?, '')
                """
            ),
            (product_text, location),
        )
        row = cur.fetchone()

        if row:
            rid = row[0] if USE_POSTGRES else row["id"]
            cur.execute(
                sql(
                    """
                    UPDATE inventory
                    SET qty = qty + ?, product_code = ?, customer_name = ?, operator = ?, source_text = ?, updated_at = ?
                    WHERE id = ?
                    """
                ),
                (qty, product_code, customer_name, operator, source_text, now(), rid),
            )
        else:
            cur.execute(
                sql(
                    """
                    INSERT INTO inventory(
                        product_text, product_code, qty, location,
                        customer_name, operator, source_text, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (product_text, product_code, qty, location, customer_name, operator, source_text, now(), now()),
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        log_error("save_inventory_item", e)
        raise
    finally:
        conn.close()


def list_inventory():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql("SELECT * FROM inventory ORDER BY updated_at DESC, id DESC"))
    rows = rows_to_dict(cur)
    conn.close()
    return rows


# =====================================
# 訂單 / 總單
# =====================================
def save_order(customer_name, items, operator):
    conn = get_db()
    cur = conn.cursor()
    try:
        for item in items:
            product_text = item.get("product_text") or item.get("product") or ""
            product_code = item.get("product_code") or ""
            qty = int(item.get("qty", item.get("quantity", 0)) or 0)
            cur.execute(
                sql(
                    """
                    INSERT INTO orders(customer_name, product_text, product_code, qty, status, operator, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
                    """
                ),
                (customer_name, product_text, product_code, qty, operator, now(), now()),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        log_error("save_order", e)
        raise
    finally:
        conn.close()


def save_master_order(customer_name, items, operator):
    conn = get_db()
    cur = conn.cursor()
    try:
        for item in items:
            product_text = item.get("product_text") or item.get("product") or ""
            product_code = item.get("product_code") or ""
            qty = int(item.get("qty", item.get("quantity", 0)) or 0)

            cur.execute(
                sql(
                    """
                    SELECT id FROM master_orders
                    WHERE customer_name = ? AND product_text = ?
                    """
                ),
                (customer_name, product_text),
            )
            row = cur.fetchone()
            if row:
                rid = row[0] if USE_POSTGRES else row["id"]
                cur.execute(
                    sql(
                        """
                        UPDATE master_orders
                        SET qty = qty + ?, product_code = ?, operator = ?, updated_at = ?
                        WHERE id = ?
                        """
                    ),
                    (qty, product_code, operator, now(), rid),
                )
            else:
                cur.execute(
                    sql(
                        """
                        INSERT INTO master_orders(customer_name, product_text, product_code, qty, operator, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """
                    ),
                    (customer_name, product_text, product_code, qty, operator, now(), now()),
                )
        conn.commit()
    except Exception as e:
        conn.rollback()
        log_error("save_master_order", e)
        raise
    finally:
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


# =====================================
# 出貨
# =====================================
def _deduct_from_table(cur, table: str, customer_name: str, product_text: str, qty_needed: int):
    cur.execute(
        sql(
            f"""
            SELECT id, qty
            FROM {table}
            WHERE customer_name = ? AND product_text = ? AND qty > 0
            ORDER BY id ASC
            """
        ),
        (customer_name, product_text),
    )
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
        cur.execute(
            sql(
                f"""
                UPDATE {table}
                SET qty = qty - ?, updated_at = ?
                WHERE id = ?
                """
            ),
            (use_qty, now(), rid),
        )
        used.append({"id": rid, "qty": use_qty})
        remain -= use_qty
        if remain <= 0:
            break

    return True, used


def _deduct_from_inventory(cur, product_text: str, qty_needed: int):
    cur.execute(
        sql(
            """
            SELECT id, qty
            FROM inventory
            WHERE product_text = ? AND qty > 0
            ORDER BY qty DESC, id ASC
            """
        ),
        (product_text,),
    )
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
        cur.execute(
            sql(
                """
                UPDATE inventory
                SET qty = qty - ?, updated_at = ?
                WHERE id = ?
                """
            ),
            (use_qty, now(), rid),
        )
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
            product_text = item.get("product_text") or item.get("product") or ""
            product_code = item.get("product_code") or ""
            qty_needed = int(item.get("qty", item.get("quantity", 0)) or 0)

            ok1, _used_master = _deduct_from_table(cur, "master_orders", customer_name, product_text, qty_needed)
            if not ok1:
                conn.rollback()
                return {"success": False, "error": f"{product_text} 總單庫存不足"}

            ok2, _used_order = _deduct_from_table(cur, "orders", customer_name, product_text, qty_needed)
            if not ok2:
                conn.rollback()
                return {"success": False, "error": f"{product_text} 訂單庫存不足"}

            ok3, _used_inv = _deduct_from_inventory(cur, product_text, qty_needed)
            if not ok3:
                conn.rollback()
                return {"success": False, "error": f"{product_text} 庫存不足"}

            cur.execute(
                sql(
                    """
                    INSERT INTO shipping_records(
                        customer_name, product_text, product_code, qty, operator, shipped_at, note
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (customer_name, product_text, product_code, qty_needed, operator, now(), "已出貨"),
            )

            breakdown.append(
                {
                    "customer_name": customer_name,
                    "product_text": product_text,
                    "product_code": product_code,
                    "qty": qty_needed,
                    "master_deduct": qty_needed,
                    "order_deduct": qty_needed,
                    "inventory_deduct": qty_needed,
                }
            )

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


# =====================================
# 倉庫格位
# =====================================
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
    cur.execute(
        sql(
            """
            SELECT * FROM warehouse_cells
            WHERE zone = ? AND column_index = ? AND slot_type = ? AND slot_number = ?
            """
        ),
        (zone, column_index, slot_type, slot_number),
    )
    row = fetchone_dict(cur)
    conn.close()
    return row


def warehouse_save_cell(zone, column_index, slot_type, slot_number, items, note=""):
    conn = get_db()
    cur = conn.cursor()
    items_json = json.dumps(items, ensure_ascii=False)

    try:
        if USE_POSTGRES:
            cur.execute(
                """
                INSERT INTO warehouse_cells(
                    zone, column_index, slot_type, slot_number, items_json, note, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (zone, column_index, slot_type, slot_number)
                DO UPDATE SET
                    items_json = EXCLUDED.items_json,
                    note = EXCLUDED.note,
                    updated_at = EXCLUDED.updated_at
                """,
                (zone, column_index, slot_type, slot_number, items_json, note, now()),
            )
        else:
            cur.execute(
                """
                INSERT INTO warehouse_cells(
                    zone, column_index, slot_type, slot_number, items_json, note, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(zone, column_index, slot_type, slot_number)
                DO UPDATE SET
                    items_json = excluded.items_json,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (zone, column_index, slot_type, slot_number, items_json, note, now()),
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        log_error("warehouse_save_cell", e)
        raise
    finally:
        conn.close()


def warehouse_move_item(from_key, to_key, product_text, qty):
    """
    from_key / to_key 格式:
    (zone, column_index, slot_type, slot_number)
    """
    conn = get_db()
    cur = conn.cursor()
    try:
        def _load(key):
            zone, column_index, slot_type, slot_number = key
            cur.execute(
                sql(
                    """
                    SELECT * FROM warehouse_cells
                    WHERE zone = ? AND column_index = ? AND slot_type = ? AND slot_number = ?
                    """
                ),
                (zone, column_index, slot_type, slot_number),
            )
            return fetchone_dict(cur)

        src = _load(from_key)
        dst = _load(to_key)

        if not src or not dst:
            return {"success": False, "error": "來源或目標格位不存在"}

        src_items = json.loads(src["items_json"] or "[]")
        dst_items = json.loads(dst["items_json"] or "[]")

        moved = []
        remain = int(qty)
        new_src = []

        for it in src_items:
            it_qty = int(it.get("qty", 0))
            it_text = it.get("product_text") or it.get("product") or ""
            if it_text == product_text and remain > 0:
                take = min(it_qty, remain)
                remain -= take
                moved.append({**it, "qty": take})
                leftover = it_qty - take
                if leftover > 0:
                    new_src.append({**it, "qty": leftover})
            else:
                new_src.append(it)

        if remain > 0:
            return {"success": False, "error": "來源格位數量不足"}

        dst_items.extend(moved)

        cur.execute(
            sql(
                """
                UPDATE warehouse_cells
                SET items_json = ?, updated_at = ?
                WHERE zone = ? AND column_index = ? AND slot_type = ? AND slot_number = ?
                """
            ),
            (json.dumps(new_src, ensure_ascii=False), now(), *from_key),
        )
        cur.execute(
            sql(
                """
                UPDATE warehouse_cells
                SET items_json = ?, updated_at = ?
                WHERE zone = ? AND column_index = ? AND slot_type = ? AND slot_number = ?
                """
            ),
            (json.dumps(dst_items, ensure_ascii=False), now(), *to_key),
        )
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        log_error("warehouse_move_item", e)
        return {"success": False, "error": "拖曳失敗"}
    finally:
        conn.close()


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


def inventory_placements():
    cells = warehouse_get_cells()
    placement = {}
    for cell in cells:
        try:
            items = json.loads(cell.get("items_json") or "[]")
        except Exception:
            items = []

        for it in items:
            key = it.get("product_text") or it.get("product") or it.get("product_code") or ""
            placement[key] = placement.get(key, 0) + int(it.get("qty", 0))
    return placement


def inventory_summary():
    rows = list_inventory()
    placement = inventory_placements()
    result = []
    for r in rows:
        key_candidates = [
            r.get("product_text") or "",
            r.get("product_code") or "",
        ]
        placed = 0
        for k in key_candidates:
            placed = max(placed, placement.get(k, 0))
        qty = int(r.get("qty", 0) or 0)
        result.append(
            {
                **r,
                "placed_qty": placed,
                "unplaced_qty": max(0, qty - placed),
                "needs_red": max(0, qty - placed) > 0,
            }
        )
    return result


# =====================================
# 搜尋 / 反查
# =====================================
def find_multiple_locations(items):
    """
    反查商品在倉庫中的位置。
    items 可接受:
      - [{"product_text":"xxx", "qty":1}, ...]
      - ["xxx", "yyy"]
      - "xxx"
    """
    if items is None:
        items = []

    if isinstance(items, str):
        items = [items]

    normalized = []
    for it in items:
        if isinstance(it, dict):
            text = (
                it.get("product_text")
                or it.get("product")
                or it.get("product_code")
                or ""
            )
        else:
            text = str(it)
        text = text.strip()
        if text:
            normalized.append(text)

    if not normalized:
        return []

    cells = warehouse_get_cells()
    result = []

    for query in normalized:
        q = query.lower()

        # 倉庫格位內的 items_json
        for cell in cells:
            try:
                items_json = json.loads(cell.get("items_json") or "[]")
            except Exception:
                items_json = []

            for it in items_json:
                product_text = (it.get("product_text") or it.get("product") or "")
                product_code = (it.get("product_code") or "")
                customer_name = (it.get("customer_name") or "")
                note = (cell.get("note") or "")
                blob = f"{product_text} {product_code} {customer_name} {note}".lower()

                if q in blob:
                    result.append(
                        {
                            "query": query,
                            "zone": cell["zone"],
                            "column_index": cell["column_index"],
                            "slot_type": cell["slot_type"],
                            "slot_number": cell["slot_number"],
                            "customer_name": customer_name,
                            "product_text": product_text,
                            "product_code": product_code,
                            "qty": int(it.get("qty", 0) or 0),
                            "note": note,
                        }
                    )

        # 同時回傳 inventory 位置，方便前端搜尋跳轉
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            sql(
                """
                SELECT product_text, product_code, qty, location, customer_name, updated_at
                FROM inventory
                WHERE lower(product_text) LIKE ? OR lower(COALESCE(product_code, '')) LIKE ? OR lower(COALESCE(customer_name, '')) LIKE ?
                ORDER BY updated_at DESC
                """
            ),
            (f"%{q}%", f"%{q}%", f"%{q}%"),
        )
        inv_rows = rows_to_dict(cur)
        conn.close()

        for row in inv_rows:
            result.append(
                {
                    "query": query,
                    "zone": None,
                    "column_index": None,
                    "slot_type": None,
                    "slot_number": None,
                    "customer_name": row.get("customer_name", ""),
                    "product_text": row.get("product_text", ""),
                    "product_code": row.get("product_code", ""),
                    "qty": int(row.get("qty", 0) or 0),
                    "location": row.get("location", ""),
                    "updated_at": row.get("updated_at", ""),
                }
            )

    return result


# =====================================
# 備份
# =====================================
def list_backups():
    try:
        files = []
        backup_dir = "backups"
        if not os.path.isdir(backup_dir):
            return {"success": True, "files": []}

        for filename in os.listdir(backup_dir):
            path = os.path.join(backup_dir, filename)
            if os.path.isfile(path):
                files.append(
                    {
                        "filename": filename,
                        "size": os.path.getsize(path),
                        "created_at": datetime.fromtimestamp(
                            os.path.getmtime(path)
                        ).strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        files.sort(key=lambda x: x["created_at"], reverse=True)
        return {"success": True, "files": files}
    except Exception as e:
        log_error("list_backups", str(e))
        return {"success": False, "files": []}


# =====================================
# 操作歷史 / 儀表板
# =====================================
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
    cur.execute(
        sql("SELECT COUNT(*) AS cnt FROM errors WHERE substr(created_at,1,10) = ?"),
        (now()[:10],),
    )
    row = fetchone_dict(cur) or {}
    conn.close()
    return int(row.get("cnt", 0))


def get_today_shipping_qty():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        sql("SELECT COALESCE(SUM(qty),0) AS total FROM shipping_records WHERE substr(shipped_at,1,10) = ?"),
        (now()[:10],),
    )
    row = fetchone_dict(cur) or {}
    conn.close()
    return int(row.get("total", 0))


# =====================================
# 常用匯出相容名稱
# =====================================
def get_inventory():
    return list_inventory()


def get_shipping_records_today(start_date=None, end_date=None):
    return get_shipping_records(start_date=start_date, end_date=end_date)
