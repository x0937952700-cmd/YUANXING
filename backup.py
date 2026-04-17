import os
import json
import shutil
from datetime import datetime
from pathlib import Path

from db import get_db, USE_POSTGRES, DATABASE_URL, query_all, log_action, now

BACKUP_FOLDER = Path("backups")
BACKUP_FOLDER.mkdir(exist_ok=True)


def backup_filename(prefix, ext):
    return BACKUP_FOLDER / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"


def prune_backups(keep=7):
    files = sorted([p for p in BACKUP_FOLDER.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[keep:]:
        try:
            p.unlink()
        except Exception:
            pass


def backup_sqlite():
    db_path = DATABASE_URL.replace("sqlite:///", "")
    target = backup_filename("sqlite_backup", "db")
    shutil.copy2(db_path, target)
    return {"success": True, "type": "sqlite", "file": str(target)}


def backup_postgres():
    tables = ["users", "settings", "customers", "inventory", "orders", "master_orders", "shipping_records", "corrections", "image_hashes", "logs", "notifications", "warehouse_cells"]
    data = {}
    for table in tables:
        try:
            data[table] = query_all(f"SELECT * FROM {table}")
        except Exception as e:
            data[table] = {"error": str(e)}
    target = backup_filename("postgres_backup", "json")
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"success": True, "type": "postgres", "file": str(target)}


def run_daily_backup():
    try:
        result = backup_postgres() if USE_POSTGRES else backup_sqlite()
        prune_backups(7)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_backups():
    files = []
    for p in sorted(BACKUP_FOLDER.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file():
            files.append({
                "filename": p.name,
                "size": p.stat().st_size,
                "created_at": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    return {"success": True, "files": files}
