import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///warehouse.db')
USE_POSTGRES = DATABASE_URL.startswith('postgres')

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras


def now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def sql(q: str) -> str:
    return q.replace('?', '%s') if USE_POSTGRES else q


def row_to_dict(row):
    if row is None:
        return None
    if USE_POSTGRES:
        return dict(row)
    return dict(row)


def rows_to_dicts(rows):
    return [row_to_dict(r) for r in rows]


def row_id(row):
    if row is None:
        return None
    return row['id'] if not USE_POSTGRES else row[0] if not hasattr(row, 'keys') else row.get('id', row[0])


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


def _table_columns(conn, table):
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
        return {r[0] if not hasattr(r, 'keys') else r['column_name'] for r in cur.fetchall()}
    cur.execute(f'PRAGMA table_info({table})')
    return {r[1] for r in cur.fetchall()}


def _ensure_column(conn, table, column, col_def):
    cols = _table_columns(conn, table)
    if column in cols:
        return
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_def}')
    else:
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_def}')


def _ensure_table_columns(conn):
    # Backward-compatible migrations for older deployments.
    specs = {
        'users': {
            'created_at': 'TEXT',
            'updated_at': 'TEXT',
        },
        'inventory': {
            'quantity': 'INTEGER DEFAULT 0',
            'location': "TEXT DEFAULT ''",
            'operator': "TEXT DEFAULT ''",
            'updated_at': 'TEXT',
        },
        'orders': {
            'shipped_qty': 'INTEGER DEFAULT 0',
            'status': "TEXT DEFAULT 'pending'",
            'operator': "TEXT DEFAULT ''",
            'created_at': 'TEXT',
            'updated_at': 'TEXT',
        },
        'master_orders': {
            'operator': "TEXT DEFAULT ''",
            'created_at': 'TEXT',
            'updated_at': 'TEXT',
        },
        'shipping_records': {
            'deduction_detail': "TEXT DEFAULT ''",
            'operator': "TEXT DEFAULT ''",
            'created_at': 'TEXT',
            'shipped_at': 'TEXT',
        },
        'corrections': {
            'updated_at': 'TEXT',
        },
        'image_hashes': {
            'created_at': 'TEXT',
        },
        'logs': {
            'username': "TEXT DEFAULT ''",
            'created_at': 'TEXT',
        },
        'errors': {
            'created_at': 'TEXT',
        },
        'customers': {
            'region': "TEXT DEFAULT '未分類'",
            'phone': "TEXT DEFAULT ''",
            'address': "TEXT DEFAULT ''",
            'special_requirements': "TEXT DEFAULT ''",
            'sort_order': 'INTEGER DEFAULT 0',
            'created_at': 'TEXT',
            'updated_at': 'TEXT',
        },
        'warehouse_cells': {
            'area': "TEXT DEFAULT 'A'",
            'col_no': 'INTEGER DEFAULT 1',
            'position': "TEXT DEFAULT 'front'",
            'label': "TEXT DEFAULT ''",
            'customer_name': "TEXT DEFAULT ''",
            'product': "TEXT DEFAULT ''",
            'quantity': 'INTEGER DEFAULT 0',
            'note': "TEXT DEFAULT ''",
            'updated_at': 'TEXT',
        },
    }
    for table, cols in specs.items():
        existing = _table_columns(conn, table)
        if not existing:
            continue
        for column, col_def in cols.items():
            if column not in existing:
                _ensure_column(conn, table, column, col_def)


def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        return conn
    path = DATABASE_URL.replace('sqlite:///', '')
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    pk = 'SERIAL PRIMARY KEY' if USE_POSTGRES else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    text_type = 'TEXT'
    int_type = 'INTEGER'

    tables = [
        f'''CREATE TABLE IF NOT EXISTS users (
            id {pk},
            username {text_type} UNIQUE NOT NULL,
            password {text_type} NOT NULL,
            created_at {text_type},
            updated_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS inventory (
            id {pk},
            product {text_type} NOT NULL,
            quantity {int_type} DEFAULT 0,
            location {text_type} DEFAULT '',
            operator {text_type} DEFAULT '',
            updated_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS orders (
            id {pk},
            customer {text_type} NOT NULL,
            product {text_type} NOT NULL,
            qty {int_type} DEFAULT 0,
            shipped_qty {int_type} DEFAULT 0,
            status {text_type} DEFAULT 'pending',
            operator {text_type} DEFAULT '',
            created_at {text_type},
            updated_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS master_orders (
            id {pk},
            customer {text_type} NOT NULL,
            product {text_type} NOT NULL,
            qty {int_type} DEFAULT 0,
            operator {text_type} DEFAULT '',
            updated_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS shipping_records (
            id {pk},
            customer {text_type} NOT NULL,
            product {text_type} NOT NULL,
            qty {int_type} DEFAULT 0,
            operator {text_type} DEFAULT '',
            deduction_detail {text_type} DEFAULT '',
            shipped_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS corrections (
            id {pk},
            wrong_text {text_type} UNIQUE NOT NULL,
            correct_text {text_type} NOT NULL,
            updated_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS image_hashes (
            id {pk},
            image_hash {text_type} UNIQUE NOT NULL,
            created_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS logs (
            id {pk},
            username {text_type} DEFAULT '',
            action {text_type} NOT NULL,
            created_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS errors (
            id {pk},
            source {text_type} NOT NULL,
            message {text_type} NOT NULL,
            created_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS customers (
            id {pk},
            name {text_type} UNIQUE NOT NULL,
            region {text_type} DEFAULT '未分類',
            phone {text_type} DEFAULT '',
            address {text_type} DEFAULT '',
            special_requirements {text_type} DEFAULT '',
            sort_order {int_type} DEFAULT 0,
            created_at {text_type},
            updated_at {text_type}
        )''',
        f'''CREATE TABLE IF NOT EXISTS warehouse_cells (
            id {pk},
            area {text_type} NOT NULL,
            col_no {int_type} NOT NULL,
            position {text_type} NOT NULL,
            label {text_type} DEFAULT '',
            customer_name {text_type} DEFAULT '',
            product {text_type} DEFAULT '',
            quantity {int_type} DEFAULT 0,
            note {text_type} DEFAULT '',
            updated_at {text_type},
            UNIQUE(area, col_no, position)
        )''',
    ]

    for t in tables:
        cur.execute(t)

    _ensure_table_columns(conn)

    # seed a few blank cells so the warehouse page has structure on first run
    for area in ('A', 'B'):
        for col_no in range(1, 13):
            for position in ('front', 'back'):
                if USE_POSTGRES:
                    cur.execute(
                        '''INSERT INTO warehouse_cells(area, col_no, position, label, updated_at)
                           VALUES(%s, %s, %s, %s, %s)
                           ON CONFLICT (area, col_no, position) DO NOTHING''',
                        (area, col_no, position, f'{area}{col_no}-{position}', now()),
                    )
                else:
                    cur.execute(
                        '''INSERT OR IGNORE INTO warehouse_cells(area, col_no, position, label, updated_at)
                           VALUES(?,?,?,?,?)''',
                        (area, col_no, position, f'{area}{col_no}-{position}', now()),
                    )

    conn.commit()
    conn.close()


# ---------------- users ----------------

def get_user(username):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT * FROM users WHERE username=?'), (username,))
    row = cur.fetchone()
    conn.close()
    return row_to_dict(row)


def create_user(username, password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('INSERT INTO users(username, password, created_at, updated_at) VALUES(?,?,?,?)'),
                (username, password, now(), now()))
    conn.commit()
    conn.close()


def update_password(username, old_password, new_password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT password FROM users WHERE username=?'), (username,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, '找不到帳號'
    current = row[0] if USE_POSTGRES else row['password']
    if current != old_password:
        conn.close()
        return False, '舊密碼錯誤'
    cur.execute(sql('UPDATE users SET password=?, updated_at=? WHERE username=?'), (new_password, now(), username))
    conn.commit()
    conn.close()
    return True, '密碼已更新'


# ---------------- logs ----------------

def log_action(username, action):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql('INSERT INTO logs(username, action, created_at) VALUES(?,?,?)'), (username or '', action, now()))
        conn.commit()
        conn.close()
    except Exception:
        pass


def log_error(source, message):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(sql('INSERT INTO errors(source, message, created_at) VALUES(?,?,?)'), (source, str(message), now()))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------------- corrections / OCR ----------------

def image_hash_exists(image_hash):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT id FROM image_hashes WHERE image_hash=?'), (image_hash,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def save_image_hash(image_hash):
    conn = get_db()
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute('''INSERT INTO image_hashes(image_hash, created_at)
                       VALUES(%s, %s)
                       ON CONFLICT (image_hash) DO NOTHING''', (image_hash, now()))
    else:
        cur.execute('''INSERT OR IGNORE INTO image_hashes(image_hash, created_at)
                       VALUES(?, ?)''', (image_hash, now()))
    conn.commit()
    conn.close()


def save_correction(wrong, correct):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('DELETE FROM corrections WHERE wrong_text=?'), (wrong,))
    cur.execute(sql('INSERT INTO corrections(wrong_text, correct_text, updated_at) VALUES(?,?,?)'), (wrong, correct, now()))
    conn.commit()
    conn.close()


def get_corrections():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT wrong_text, correct_text FROM corrections')
    rows = cur.fetchall()
    conn.close()
    return {r[0] if USE_POSTGRES else r['wrong_text']: r[1] if USE_POSTGRES else r['correct_text'] for r in rows}


def get_known_products():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT product FROM inventory WHERE product IS NOT NULL AND product<>""')
    rows = cur.fetchall()
    conn.close()
    return [r[0] if USE_POSTGRES else r['product'] for r in rows]


# ---------------- inventory ----------------

def save_inventory(item):
    product = (item.get('product') or '').strip()
    qty = int(item.get('quantity') or 0)
    location = (item.get('location') or '').strip()
    operator = (item.get('operator') or '').strip()
    if not product or qty <= 0:
        return
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT id FROM inventory WHERE product=? AND location=?'), (product, location))
    row = cur.fetchone()
    if row:
        _id = row[0] if USE_POSTGRES else row['id']
        cur.execute(sql('UPDATE inventory SET quantity=quantity+?, operator=?, updated_at=? WHERE id=?'), (qty, operator, now(), _id))
    else:
        cur.execute(sql('INSERT INTO inventory(product, quantity, location, operator, updated_at) VALUES(?,?,?,?,?)'),
                    (product, qty, location, operator, now()))
    conn.commit()
    conn.close()


def list_inventory():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT * FROM inventory ORDER BY product ASC, location ASC, id DESC'))
    rows = rows_to_dicts(cur.fetchall())
    cur.execute(sql('SELECT product, customer_name, label, area, col_no, position FROM warehouse_cells WHERE quantity > 0 OR product <> '' OR customer_name <> '''))
    placements = rows_to_dicts(cur.fetchall())
    conn.close()

    for row in rows:
        product = (row.get('product') or '').strip()
        matched = []
        for cell in placements:
            if not product:
                continue
            cell_product = (cell.get('product') or '').strip()
            cell_customer = (cell.get('customer_name') or '').strip()
            cell_label = (cell.get('label') or '').strip()
            if product == cell_product or product == cell_customer or product in cell_product or product in cell_label:
                matched.append(f"{cell.get('area', '')}{cell.get('col_no', '')}{('前' if cell.get('position') == 'front' else '後')}")
        row['warehouse_locations'] = matched
        row['is_placed'] = bool(matched)
    return rows


# ---------------- orders ----------------

def save_order(customer, items, operator):
    customer = (customer or '').strip()
    conn = get_db()
    cur = conn.cursor()
    saved = []
    for item in items or []:
        product = (item.get('product') or '').strip()
        qty = int(item.get('quantity') or 0)
        if not product or qty <= 0:
            continue
        cur.execute(sql('''INSERT INTO orders(customer, product, qty, shipped_qty, status, operator, created_at, updated_at)
                           VALUES(?,?,?,?,?,?,?,?)'''),
                    (customer, product, qty, 0, 'pending', operator, now(), now()))
        saved.append({'product': product, 'qty': qty})
    conn.commit()
    conn.close()
    return saved


def save_master_order(customer, items, operator):
    customer = (customer or '').strip()
    conn = get_db()
    cur = conn.cursor()
    saved = []
    for item in items or []:
        product = (item.get('product') or '').strip()
        qty = int(item.get('quantity') or 0)
        if not product or qty <= 0:
            continue
        cur.execute(sql('SELECT id FROM master_orders WHERE customer=? AND product=?'), (customer, product))
        row = cur.fetchone()
        if row:
            _id = row[0] if USE_POSTGRES else row['id']
            cur.execute(sql('UPDATE master_orders SET qty=qty+?, operator=?, updated_at=? WHERE id=?'), (qty, operator, now(), _id))
        else:
            cur.execute(sql('INSERT INTO master_orders(customer, product, qty, operator, updated_at) VALUES(?,?,?,?,?)'),
                        (customer, product, qty, operator, now()))
        saved.append({'product': product, 'qty': qty})
    conn.commit()
    conn.close()
    return saved


def list_orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT * FROM orders ORDER BY id DESC'))
    rows = rows_to_dicts(cur.fetchall())
    conn.close()
    return rows


def list_master_orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT * FROM master_orders ORDER BY customer ASC, product ASC, id DESC'))
    rows = rows_to_dicts(cur.fetchall())
    conn.close()
    return rows


def ship_order(customer, items, operator):
    customer = (customer or '').strip()
    conn = get_db()
    cur = conn.cursor()
    details = []
    try:
        for item in items or []:
            product = (item.get('product') or '').strip()
            qty_needed = int(item.get('quantity') or 0)
            if not product or qty_needed <= 0:
                continue

            remaining = qty_needed
            steps = []

            # 1) deduct from master orders
            cur.execute(sql('SELECT id, qty FROM master_orders WHERE customer=? AND product=? ORDER BY id ASC'), (customer, product))
            master_rows = cur.fetchall()
            for r in master_rows:
                mid = r[0] if USE_POSTGRES else r['id']
                available = r[1] if USE_POSTGRES else r['qty']
                if remaining <= 0:
                    break
                take = min(available, remaining)
                if take > 0:
                    cur.execute(sql('UPDATE master_orders SET qty=qty-?, updated_at=? WHERE id=?'), (take, now(), mid))
                    remaining -= take
                    steps.append(f'總單-{take}')

            # 2) deduct from orders
            if remaining > 0:
                cur.execute(sql('SELECT id, qty, shipped_qty FROM orders WHERE customer=? AND product=? AND status IN (?, ?, ?) ORDER BY id ASC'),
                            (customer, product, 'pending', 'partial', 'processing'))
                order_rows = cur.fetchall()
                for r in order_rows:
                    oid = r[0] if USE_POSTGRES else r['id']
                    qty = r[1] if USE_POSTGRES else r['qty']
                    shipped_qty = r[2] if USE_POSTGRES else r['shipped_qty']
                    available = max(int(qty) - int(shipped_qty), 0)
                    if remaining <= 0:
                        break
                    take = min(available, remaining)
                    if take > 0:
                        new_shipped = int(shipped_qty) + take
                        new_status = 'shipped' if new_shipped >= int(qty) else 'partial'
                        cur.execute(sql('UPDATE orders SET shipped_qty=?, status=?, updated_at=? WHERE id=?'),
                                    (new_shipped, new_status, now(), oid))
                        remaining -= take
                        steps.append(f'訂單-{take}')

            # 3) deduct from inventory
            if remaining > 0:
                cur.execute(sql('SELECT id, quantity FROM inventory WHERE product=? AND quantity>0 ORDER BY quantity DESC, id ASC'), (product,))
                inv_rows = cur.fetchall()
                total_stock = 0
                for r in inv_rows:
                    total_stock += r[1] if USE_POSTGRES else r['quantity']
                if total_stock < remaining:
                    raise ValueError(f'{product} 庫存不足')
                for r in inv_rows:
                    if remaining <= 0:
                        break
                    iid = r[0] if USE_POSTGRES else r['id']
                    stock = r[1] if USE_POSTGRES else r['quantity']
                    take = min(stock, remaining)
                    if take > 0:
                        cur.execute(sql('UPDATE inventory SET quantity=quantity-?, updated_at=? WHERE id=?'), (take, now(), iid))
                        remaining -= take
                        steps.append(f'庫存-{take}')

            deduction_detail = ' / '.join(steps) if steps else '無扣除'
            cur.execute(sql('''INSERT INTO shipping_records(customer, product, qty, operator, deduction_detail, shipped_at)
                               VALUES(?,?,?,?,?,?)'''),
                        (customer, product, qty_needed, operator, deduction_detail, now()))
            details.append({'customer': customer, 'product': product, 'qty': qty_needed, 'detail': deduction_detail})

        conn.commit()
        return {'success': True, 'details': details, 'message': '出貨成功'}
    except Exception as e:
        conn.rollback()
        log_error('ship_order', e)
        return {'success': False, 'error': str(e) or '出貨失敗'}
    finally:
        conn.close()


def get_shipping_records(days=None):
    conn = get_db()
    cur = conn.cursor()
    if days:
        try:
            days = int(days)
        except Exception:
            days = None
    if days:
        if USE_POSTGRES:
            cur.execute(sql('SELECT * FROM shipping_records WHERE shipped_at >= (NOW() - INTERVAL \"1 day\" * ?) ORDER BY id DESC'), (days,))
        else:
            # sqlite date math with stored string values is harder; use python filter below
            cur.execute(sql('SELECT * FROM shipping_records ORDER BY id DESC'))
            rows = rows_to_dicts(cur.fetchall())
            conn.close()
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=days)
            return [r for r in rows if r.get('shipped_at') and datetime.strptime(r['shipped_at'], '%Y-%m-%d %H:%M:%S') >= cutoff]
    else:
        cur.execute(sql('SELECT * FROM shipping_records ORDER BY id DESC'))
    rows = rows_to_dicts(cur.fetchall())
    conn.close()
    return rows


# ---------------- customers ----------------

def list_customers():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT * FROM customers ORDER BY region ASC, sort_order ASC, name ASC'))
    rows = rows_to_dicts(cur.fetchall())
    conn.close()
    return rows


def save_customer(customer):
    name = (customer.get('name') or '').strip()
    region = (customer.get('region') or '未分類').strip()
    phone = (customer.get('phone') or '').strip()
    address = (customer.get('address') or '').strip()
    special_requirements = (customer.get('special_requirements') or '').strip()
    sort_order = int(customer.get('sort_order') or 0)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT id FROM customers WHERE name=?'), (name,))
    row = cur.fetchone()
    if row:
        cid = row[0] if USE_POSTGRES else row['id']
        cur.execute(sql('''UPDATE customers SET region=?, phone=?, address=?, special_requirements=?, sort_order=?, updated_at=? WHERE id=?'''),
                    (region, phone, address, special_requirements, sort_order, now(), cid))
    else:
        cur.execute(sql('''INSERT INTO customers(name, region, phone, address, special_requirements, sort_order, created_at, updated_at)
                           VALUES(?,?,?,?,?,?,?,?)'''),
                    (name, region, phone, address, special_requirements, sort_order, now(), now()))
    conn.commit()
    conn.close()


def reorder_customers(region, ordered_names):
    conn = get_db()
    cur = conn.cursor()
    for idx, name in enumerate(ordered_names or []):
        cur.execute(sql('UPDATE customers SET sort_order=?, region=?, updated_at=? WHERE name=?'), (idx, region, now(), name))
    conn.commit()
    conn.close()


def delete_customer(name):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('DELETE FROM customers WHERE name=?'), (name,))
    conn.commit()
    conn.close()


# ---------------- warehouse ----------------

def list_warehouse_cells():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT * FROM warehouse_cells ORDER BY area ASC, col_no ASC, position ASC, id ASC'))
    rows = rows_to_dicts(cur.fetchall())
    conn.close()
    return rows


def upsert_warehouse_cell(cell):
    area = (cell.get('area') or 'A').strip().upper()
    col_no = int(cell.get('col_no') or 1)
    position = (cell.get('position') or 'front').strip().lower()
    label = (cell.get('label') or '').strip()
    customer_name = (cell.get('customer_name') or '').strip()
    product = (cell.get('product') or '').strip()
    quantity = int(cell.get('quantity') or 0)
    note = (cell.get('note') or '').strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('SELECT id FROM warehouse_cells WHERE area=? AND col_no=? AND position=?'), (area, col_no, position))
    row = cur.fetchone()
    if row:
        cid = row[0] if USE_POSTGRES else row['id']
        cur.execute(sql('''UPDATE warehouse_cells SET label=?, customer_name=?, product=?, quantity=?, note=?, updated_at=? WHERE id=?'''),
                    (label, customer_name, product, quantity, note, now(), cid))
    else:
        cur.execute(sql('''INSERT INTO warehouse_cells(area, col_no, position, label, customer_name, product, quantity, note, updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?)'''),
                    (area, col_no, position, label, customer_name, product, quantity, note, now()))
    conn.commit()
    conn.close()


def delete_warehouse_cell(area, col_no, position):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql('DELETE FROM warehouse_cells WHERE area=? AND col_no=? AND position=?'), (area, int(col_no), position))
    conn.commit()
    conn.close()


def find_multiple_locations(items):
    conn = get_db()
    cur = conn.cursor()
    results = []
    for item in items or []:
        if isinstance(item, dict):
            product = (item.get('product') or item.get('name') or '').strip()
        else:
            product = str(item).strip()
        if not product:
            continue
        cur.execute(sql('SELECT product, location, quantity, operator, updated_at FROM inventory WHERE product LIKE ? AND quantity > 0 ORDER BY quantity DESC'), (f'%{product}%',))
        for r in rows_to_dicts(cur.fetchall()):
            results.append({
                'product': r['product'],
                'location': r.get('location', ''),
                'quantity': r.get('quantity', 0),
                'type': 'inventory',
            })
        cur.execute(sql('SELECT area, col_no, position, label, customer_name, product, quantity, note, updated_at FROM warehouse_cells WHERE product LIKE ? OR customer_name LIKE ? OR label LIKE ? ORDER BY area ASC, col_no ASC, position ASC'), (f'%{product}%', f'%{product}%', f'%{product}%'))
        for r in rows_to_dicts(cur.fetchall()):
            results.append({
                'product': r.get('product', ''),
                'location': f"{r['area']}區 {r['col_no']}欄 {r['position']}",
                'quantity': r.get('quantity', 0),
                'customer_name': r.get('customer_name', ''),
                'type': 'warehouse',
            })
    conn.close()
    return results
