
import json
import os
import shutil
from datetime import datetime

from db import get_db, USE_POSTGRES, DATABASE_URL, list_settings, log_error

BACKUP_FOLDER = "backups"
os.makedirs(BACKUP_FOLDER, exist_ok=True)


def backup_filename(prefix, ext):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(BACKUP_FOLDER, f"{prefix}_{timestamp}.{ext}")


def prune_old_backups(keep=7):
    files = []
    for fn in os.listdir(BACKUP_FOLDER):
        path = os.path.join(BACKUP_FOLDER, fn)
        if os.path.isfile(path):
            files.append((os.path.getmtime(path), path))
    files.sort(reverse=True)
    for _, path in files[keep:]:
        try:
            os.remove(path)
        except Exception:
            pass


def backup_sqlite():
    try:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        target = backup_filename("sqlite_backup", "db")
        shutil.copy2(db_path, target)
        prune_old_backups()
        return {"success": True, "type": "sqlite", "file": target}
    except Exception as e:
        log_error("backup_sqlite", str(e))
        return {"success": False, "error": str(e)}


def backup_postgres():
    try:
        conn = get_db()
        cur = conn.cursor()
        tables = [
            "users", "settings", "customers", "inventory", "orders", "master_orders",
            "shipping_records", "corrections", "image_hashes", "logs", "errors",
            "notifications", "warehouse_cells"
        ]
        backup_data = {}
        for table in tables:
            cur.execute(f"SELECT * FROM {table}")
            cols = [d[0] for d in cur.description]
            backup_data[table] = [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.close()
        target = backup_filename("postgres_backup", "json")
        with open(target, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        prune_old_backups()
        return {"success": True, "type": "postgres", "file": target}
    except Exception as e:
        log_error("backup_postgres", str(e))
        return {"success": False, "error": str(e)}


def backup_images():
    try:
        source_dir = "uploads"
        target_dir = backup_filename("images_backup", "dir")
        os.makedirs(target_dir, exist_ok=True)
        if os.path.isdir(source_dir):
            for fn in os.listdir(source_dir):
                src = os.path.join(source_dir, fn)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(target_dir, fn))
        prune_old_backups()
        return {"success": True, "type": "images", "file": target_dir}
    except Exception as e:
        log_error("backup_images", str(e))
        return {"success": False, "error": str(e)}


def run_daily_backup():
    try:
        db_result = backup_postgres() if USE_POSTGRES else backup_sqlite()
        img_result = backup_images()
        return {"success": db_result.get("success", False) and img_result.get("success", False), "db": db_result, "images": img_result}
    except Exception as e:
        log_error("run_daily_backup", str(e))
        return {"success": False, "error": str(e)}


def list_backups():
    try:
        files = []
        for filename in os.listdir(BACKUP_FOLDER):
            path = os.path.join(BACKUP_FOLDER, filename)
            if os.path.isfile(path):
                files.append({
                    "filename": filename,
                    "size": os.path.getsize(path),
                    "created_at": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
                })
        files.sort(key=lambda x: x["created_at"], reverse=True)
        return {"success": True, "files": files}
    except Exception as e:
        log_error("list_backups", str(e))
        return {"success": False, "files": []}
