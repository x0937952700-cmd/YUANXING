import json
import os
import shutil
import zipfile
from datetime import datetime

from db import get_db, USE_POSTGRES, DATABASE_URL, log_error

BACKUP_FOLDER = 'backups'
UPLOAD_FOLDER = 'uploads'
os.makedirs(BACKUP_FOLDER, exist_ok=True)


def _timestamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _cleanup_old_backups(prefix, keep=7):
    files = []
    for filename in os.listdir(BACKUP_FOLDER):
        if filename.startswith(prefix):
            files.append(os.path.join(BACKUP_FOLDER, filename))
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for old in files[keep:]:
        try:
            os.remove(old)
        except Exception:
            pass


def backup_sqlite():
    try:
        db_path = DATABASE_URL.replace('sqlite:///', '')
        target = os.path.join(BACKUP_FOLDER, f'sqlite_backup_{_timestamp()}.db')
        shutil.copy2(db_path, target)
        _cleanup_old_backups('sqlite_backup_')
        return {'success': True, 'type': 'sqlite', 'file': target}
    except Exception as e:
        log_error('backup_sqlite', str(e))
        return {'success': False, 'error': str(e)}


def backup_postgres():
    try:
        conn = get_db()
        cur = conn.cursor()
        tables = ['users', 'inventory', 'orders', 'master_orders', 'shipping_records', 'corrections', 'image_hashes', 'logs', 'errors', 'customers', 'warehouse_cells']
        backup_data = {}
        for table in tables:
            cur.execute(f'SELECT * FROM {table}')
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
            backup_data[table] = [dict(zip(columns, row)) for row in rows]
        conn.close()

        target = os.path.join(BACKUP_FOLDER, f'postgres_backup_{_timestamp()}.json')
        with open(target, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        _cleanup_old_backups('postgres_backup_')
        return {'success': True, 'type': 'postgres', 'file': target}
    except Exception as e:
        log_error('backup_postgres', str(e))
        return {'success': False, 'error': str(e)}


def backup_uploads():
    try:
        target = os.path.join(BACKUP_FOLDER, f'uploads_backup_{_timestamp()}.zip')
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as zf:
            if os.path.isdir(UPLOAD_FOLDER):
                for root, _, files in os.walk(UPLOAD_FOLDER):
                    for file in files:
                        path = os.path.join(root, file)
                        arc = os.path.relpath(path, '.')
                        zf.write(path, arc)
        _cleanup_old_backups('uploads_backup_')
        return {'success': True, 'type': 'uploads', 'file': target}
    except Exception as e:
        log_error('backup_uploads', str(e))
        return {'success': False, 'error': str(e)}


def run_daily_backup():
    try:
        db_result = backup_postgres() if USE_POSTGRES else backup_sqlite()
        up_result = backup_uploads()
        return {
            'success': db_result.get('success', False) and up_result.get('success', False),
            'db_backup': db_result,
            'uploads_backup': up_result,
        }
    except Exception as e:
        log_error('run_daily_backup', str(e))
        return {'success': False, 'error': str(e)}


def list_backups():
    try:
        files = []
        for filename in os.listdir(BACKUP_FOLDER):
            path = os.path.join(BACKUP_FOLDER, filename)
            if os.path.isfile(path):
                files.append({
                    'filename': filename,
                    'size': os.path.getsize(path),
                    'created_at': datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S'),
                })
        files.sort(key=lambda x: x['created_at'], reverse=True)
        return {'success': True, 'files': files}
    except Exception as e:
        log_error('list_backups', str(e))
        return {'success': False, 'files': []}
