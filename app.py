from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import timedelta
import hashlib
import json
import os
from functools import wraps
from PIL import Image

from db import (
    init_db,
    get_user,
    create_user,
    update_password,
    log_action,
    save_inventory,
    save_order,
    save_master_order,
    ship_order,
    get_shipping_records,
    save_correction,
    find_multiple_locations,
    log_error,
    save_image_hash,
    image_hash_exists,
    list_inventory,
    list_orders,
    list_master_orders,
    list_customers,
    save_customer,
    reorder_customers,
    delete_customer,
    list_warehouse_cells,
    upsert_warehouse_cell,
    delete_warehouse_cell,
)
from ocr import process_ocr_text
from backup import run_daily_backup, list_backups

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'warehouse-secret-key')
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER = 'uploads'
BACKUP_FOLDER = 'backups'
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
MAX_UPLOAD_SIZE = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE

init_db()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def require_login():
    return 'user' in session


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not require_login():
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': '請先登入'}), 401
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return wrapper


def error_response(msg, code=200):
    return jsonify({'success': False, 'error': msg}), code


def ok_response(**kwargs):
    payload = {'success': True}
    payload.update(kwargs)
    return jsonify(payload)


def compress_image(path):
    try:
        img = Image.open(path)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        if img.width > 1600:
            ratio = 1600 / float(img.width)
            img = img.resize((1600, int(img.height * ratio)))
        img.save(path, 'JPEG', quality=78, optimize=True)
    except Exception as e:
        log_error('compress_image', str(e))


def save_upload_content(file_storage):
    content = file_storage.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise ValueError('圖片過大')
    image_hash = hashlib.md5(content).hexdigest()
    if image_hash_exists(image_hash):
        raise ValueError('此圖片已上傳過')
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    filename = f'{image_hash}.{ext}'
    path = os.path.join(UPLOAD_FOLDER, filename)
    with open(path, 'wb') as f:
        f.write(content)
    compress_image(path)
    save_image_hash(image_hash)
    return path


# ---------------- pages ----------------
@app.route('/')
@login_required
def home():
    return render_template('index.html', username=session.get('user', ''))


@app.route('/login')
def login_page():
    if require_login():
        return redirect(url_for('home'))
    return render_template('login.html')


@app.route('/inventory')
@login_required
def inventory_page():
    return render_template('module.html', page_key='inventory', page_title='庫存', username=session.get('user', ''))


@app.route('/order')
@login_required
def order_page():
    return render_template('module.html', page_key='order', page_title='訂單', username=session.get('user', ''))


@app.route('/master-order')
@login_required
def master_order_page():
    return render_template('module.html', page_key='master_order', page_title='總單', username=session.get('user', ''))


@app.route('/ship')
@login_required
def ship_page():
    return render_template('module.html', page_key='ship', page_title='出貨', username=session.get('user', ''))


@app.route('/shipping-records')
@login_required
def shipping_records_page():
    return render_template('module.html', page_key='shipping_records', page_title='出貨查詢', username=session.get('user', ''))


@app.route('/warehouse')
@login_required
def warehouse_page():
    return render_template('module.html', page_key='warehouse', page_title='倉庫圖', username=session.get('user', ''))


@app.route('/customers')
@login_required
def customers_page():
    return render_template('module.html', page_key='customers', page_title='客戶資料', username=session.get('user', ''))


@app.route('/settings')
@login_required
def settings_page():
    return render_template('module.html', page_key='settings', page_title='設定', username=session.get('user', ''))


# ---------------- auth ----------------
@app.route('/api/login', methods=['POST'])
def login_api():
    try:
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict() or {}

        username = (data.get('username') or data.get('name') or '').strip()
        password = (data.get('password') or '').strip()

        if not username or not password:
            return error_response('帳號密碼不可空白')

        user = get_user(username)
        if not user:
            create_user(username, password)
            log_action(username, '建立帳號')
        elif user.get('password') != password:
            return error_response('密碼錯誤')

        session.permanent = True
        session['user'] = username
        log_action(username, '登入系統')
        return ok_response(username=username)
    except Exception as e:
        log_error('login_api', str(e))
        return error_response('登入失敗')


@app.route('/api/logout', methods=['POST'])
@login_required
def logout_api():
    user = session.get('user', '')
    session.clear()
    log_action(user, '登出系統')
    return ok_response()


@app.route('/api/change_password', methods=['POST'])
@login_required
def change_password_api():
    try:
        data = request.get_json(force=True) or {}
        old_password = (data.get('old_password') or '').strip()
        new_password = (data.get('new_password') or '').strip()
        confirm_password = (data.get('confirm_password') or '').strip()
        if not old_password or not new_password or not confirm_password:
            return error_response('請填完整')
        if new_password != confirm_password:
            return error_response('兩次密碼不一致')
        ok, msg = update_password(session.get('user', ''), old_password, new_password)
        if not ok:
            return error_response(msg)
        log_action(session.get('user', ''), '修改密碼')
        return ok_response(message=msg)
    except Exception as e:
        log_error('change_password_api', str(e))
        return error_response('修改失敗')


# ---------------- OCR ----------------
@app.route('/api/upload_ocr', methods=['POST'])
@login_required
def upload_ocr_api():
    try:
        file = request.files.get('file')
        if not file:
            return error_response('未選擇圖片')
        if not allowed_file(file.filename):
            return error_response('格式錯誤')
        path = save_upload_content(file)
        result = process_ocr_text(path)
        confidence = result.get('confidence', 0)
        log_action(session.get('user', ''), 'OCR辨識')
        return ok_response(
            text=result.get('text', ''),
            items=result.get('items', []),
            confidence=confidence,
            warning='辨識信心偏低，請確認內容' if confidence < 80 else '',
            sync_time=int(os.path.getmtime(path)),
            image_path=f'/{path}',
        )
    except Exception as e:
        log_error('upload_ocr_api', str(e))
        msg = str(e)
        if '圖片過大' in msg:
            return error_response('圖片過大')
        if '上傳過' in msg:
            return error_response('此圖片已上傳過')
        return error_response('OCR失敗')


@app.route('/api/save_correction', methods=['POST'])
@login_required
def save_correction_api():
    try:
        data = request.get_json(force=True) or {}
        wrong = (data.get('wrong_text') or '').strip()
        correct = (data.get('correct_text') or '').strip()
        if wrong and correct and wrong != correct:
            save_correction(wrong, correct)
            log_action(session.get('user', ''), f'修正OCR {wrong}->{correct}')
        return ok_response()
    except Exception as e:
        log_error('save_correction_api', str(e))
        return error_response('儲存失敗')


# ---------------- inventory / orders / ship ----------------
@app.route('/api/inventory', methods=['GET', 'POST'])
@login_required
def inventory_api():
    try:
        if request.method == 'GET':
            return ok_response(items=list_inventory())
        data = request.get_json(force=True) or {}
        items = data.get('items', [])
        saved = []
        for item in items:
            save_inventory({**item, 'operator': session.get('user', '')})
            saved.append(item)
        log_action(session.get('user', ''), '建立庫存')
        return ok_response(saved=saved, inventory=list_inventory(), message='庫存已更新')
    except Exception as e:
        log_error('inventory_api', str(e))
        return error_response('建立失敗')


@app.route('/api/order', methods=['GET', 'POST'])
@login_required
def order_api():
    try:
        if request.method == 'GET':
            return ok_response(items=list_orders())
        data = request.get_json(force=True) or {}
        customer = data.get('customer') or ''
        items = data.get('items', [])
        saved = save_order(customer, items, session.get('user', ''))
        log_action(session.get('user', ''), '建立訂單')
        return ok_response(saved=saved, orders=list_orders(), message='訂單已建立')
    except Exception as e:
        log_error('order_api', str(e))
        return error_response('訂單建立失敗')


@app.route('/api/master_order', methods=['GET', 'POST'])
@login_required
def master_order_api():
    try:
        if request.method == 'GET':
            return ok_response(items=list_master_orders())
        data = request.get_json(force=True) or {}
        customer = data.get('customer') or ''
        items = data.get('items', [])
        saved = save_master_order(customer, items, session.get('user', ''))
        log_action(session.get('user', ''), '更新總單')
        return ok_response(saved=saved, master_orders=list_master_orders(), message='總單已更新')
    except Exception as e:
        log_error('master_order_api', str(e))
        return error_response('總單失敗')


@app.route('/api/ship', methods=['POST'])
@login_required
def ship_api():
    try:
        data = request.get_json(force=True) or {}
        customer = data.get('customer') or ''
        items = data.get('items', [])
        confirm = data.get('confirm', False)
        if not confirm:
            return error_response('出貨前請再次確認')
        result = ship_order(customer, items, session.get('user', ''))
        if result.get('success'):
            log_action(session.get('user', ''), '完成出貨')
        return jsonify(result)
    except Exception as e:
        log_error('ship_api', str(e))
        return error_response('出貨失敗')


@app.route('/api/shipping_records', methods=['GET'])
@login_required
def shipping_records_api():
    days = request.args.get('days')
    records = get_shipping_records(days=days)
    return ok_response(records=records)


@app.route('/api/find_locations', methods=['POST'])
@login_required
def find_locations_api():
    try:
        data = request.get_json(force=True) or {}
        items = data.get('items', [])
        return ok_response(items=find_multiple_locations(items))
    except Exception as e:
        log_error('find_locations_api', str(e))
        return error_response('定位失敗')


# ---------------- customers ----------------
@app.route('/api/customers', methods=['GET', 'POST'])
@login_required
def customers_api():
    try:
        if request.method == 'GET':
            return ok_response(customers=list_customers())
        data = request.get_json(force=True) or {}
        save_customer(data)
        log_action(session.get('user', ''), f'更新客戶 {data.get("name", "")}')
        return ok_response(customers=list_customers(), message='客戶已更新')
    except Exception as e:
        log_error('customers_api', str(e))
        return error_response('客戶儲存失敗')


@app.route('/api/customers/delete', methods=['POST'])
@login_required
def customers_delete_api():
    try:
        data = request.get_json(force=True) or {}
        name = (data.get('name') or '').strip()
        if not name:
            return error_response('缺少客戶名稱')
        delete_customer(name)
        log_action(session.get('user', ''), f'刪除客戶 {name}')
        return ok_response(customers=list_customers())
    except Exception as e:
        log_error('customers_delete_api', str(e))
        return error_response('刪除失敗')


@app.route('/api/customers/reorder', methods=['POST'])
@login_required
def customers_reorder_api():
    try:
        data = request.get_json(force=True) or {}
        region = data.get('region') or '未分類'
        ordered_names = data.get('ordered_names') or []
        reorder_customers(region, ordered_names)
        log_action(session.get('user', ''), f'調整客戶排序 {region}')
        return ok_response(customers=list_customers())
    except Exception as e:
        log_error('customers_reorder_api', str(e))
        return error_response('排序失敗')


# ---------------- warehouse ----------------
@app.route('/api/warehouse', methods=['GET', 'POST'])
@login_required
def warehouse_api():
    try:
        if request.method == 'GET':
            return ok_response(cells=list_warehouse_cells())
        data = request.get_json(force=True) or {}
        upsert_warehouse_cell(data)
        log_action(session.get('user', ''), f'更新倉庫格位 {data.get("area","")}{data.get("col_no","")}-{data.get("position","")}')
        return ok_response(cells=list_warehouse_cells(), message='倉庫格位已更新')
    except Exception as e:
        log_error('warehouse_api', str(e))
        return error_response('倉庫儲存失敗')


@app.route('/api/warehouse/delete', methods=['POST'])
@login_required
def warehouse_delete_api():
    try:
        data = request.get_json(force=True) or {}
        delete_warehouse_cell(data.get('area'), data.get('col_no'), data.get('position'))
        log_action(session.get('user', ''), f'刪除倉庫格位 {data.get("area","")}{data.get("col_no","")}-{data.get("position","")}')
        return ok_response(cells=list_warehouse_cells())
    except Exception as e:
        log_error('warehouse_delete_api', str(e))
        return error_response('刪除失敗')


# ---------------- backup / logs ----------------
@app.route('/api/backup', methods=['POST', 'GET'])
@login_required
def backup_api():
    result = run_daily_backup()
    log_action(session.get('user', ''), '手動備份')
    return jsonify(result)


@app.route('/api/backups', methods=['GET'])
@login_required
def backups_api():
    return jsonify(list_backups())


@app.route('/health')
def health():
    return 'OK'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
