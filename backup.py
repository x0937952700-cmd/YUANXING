import json
import os
import shutil
from datetime import datetime

from config import Config
from extensions import db

BACKUP_FOLDER = "backups"
os.makedirs(BACKUP_FOLDER, exist_ok=True)

TABLES = [
    "users",
    "customers",
    "warehouse_slots",
    "inventory_items",
    "orders",
    "order_items",
    "master_order_items",
    "shipments",
    "activity_logs",
    "user_activity_states",
]


def _backup_filename(prefix: str, ext: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(BACKUP_FOLDER, f"{prefix}_{timestamp}.{ext}")


def _trim_backups(prefix: str, keep: int = 7) -> None:
    files = sorted([f for f in os.listdir(BACKUP_FOLDER) if f.startswith(prefix + "_")])
    while len(files) > keep:
        old = files.pop(0)
        try:
            os.remove(os.path.join(BACKUP_FOLDER, old))
        except Exception:
            pass


def backup_sqlite() -> dict:
    try:
        uri = Config.SQLALCHEMY_DATABASE_URI
        if not uri.startswith("sqlite:///"):
            return {"success": False, "error": "目前不是 SQLite 資料庫"}
        db_path = uri.replace("sqlite:///", "", 1)
        target = _backup_filename("sqlite_backup", "db")
        shutil.copy2(db_path, target)
        _trim_backups("sqlite_backup")
        return {"success": True, "type": "sqlite", "file": target}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def backup_sqlalchemy_tables() -> dict:
    try:
        payload = {}
        with db.engine.begin() as connection:
            for table in TABLES:
                rows = connection.exec_driver_sql(f"SELECT * FROM {table}")
                payload[table] = [dict(row._mapping) for row in rows]
        target = _backup_filename("database_backup", "json")
        with open(target, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        _trim_backups("database_backup")
        return {"success": True, "type": "json", "file": target}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def run_daily_backup() -> dict:
    uri = Config.SQLALCHEMY_DATABASE_URI
    if uri.startswith("sqlite:///"):
        return backup_sqlite()
    return backup_sqlalchemy_tables()


def list_backups() -> dict:
    try:
        files = []
        for filename in os.listdir(BACKUP_FOLDER):
            path = os.path.join(BACKUP_FOLDER, filename)
            if os.path.isfile(path):
                files.append(
                    {
                        "filename": filename,
                        "size": os.path.getsize(path),
                        "created_at": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
        files.sort(key=lambda x: x["created_at"], reverse=True)
        return {"success": True, "files": files}
    except Exception:
        return {"success": True, "files": []}
