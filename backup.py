import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from db import get_db, USE_POSTGRES, DATABASE_URL, log_error

BACKUP_FOLDER = Path("backups")
UPLOAD_FOLDER = Path("uploads")
KEEP_BACKUPS = 7

BACKUP_FOLDER.mkdir(parents=True, exist_ok=True)
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


def backup_dir_name():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return BACKUP_FOLDER / f"backup_{timestamp}"


def folder_size(path: Path) -> int:
    total = 0
    if path.is_file():
        return path.stat().st_size
    for child in path.rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def cleanup_old_backups(keep: int = KEEP_BACKUPS):
    backups = [p for p in BACKUP_FOLDER.iterdir() if p.is_dir() and p.name.startswith("backup_")]
    backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for old in backups[keep:]:
        try:
            shutil.rmtree(old, ignore_errors=True)
        except Exception as e:
            log_error("cleanup_old_backups", str(e))


def backup_sqlite(target_dir: Path):
    db_path = Path(DATABASE_URL.replace("sqlite:///", ""))
    target = target_dir / "database.db"
    shutil.copy2(db_path, target)
    return {
        "success": True,
        "type": "sqlite",
        "file": str(target)
    }


def backup_postgres(target_dir: Path):
    conn = get_db()
    cur = conn.cursor()

    tables = [
        "users",
        "inventory",
        "orders",
        "master_orders",
        "shipping_records",
        "corrections",
        "image_hashes",
        "logs",
        "errors"
    ]

    backup_data = {}
    for table in tables:
        cur.execute(f"SELECT * FROM {table}")
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        backup_data[table] = [dict(zip(columns, row)) for row in rows]

    conn.close()

    target = target_dir / "database.json"
    with open(target, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "type": "postgres",
        "file": str(target)
    }


def backup_images(target_dir: Path):
    images_dir = target_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for file in UPLOAD_FOLDER.iterdir():
        if file.is_file() and file.name != ".gitkeep":
            shutil.copy2(file, images_dir / file.name)
            copied += 1

    return {
        "success": True,
        "type": "images",
        "count": copied,
        "folder": str(images_dir)
    }


def run_daily_backup():
    try:
        target_dir = backup_dir_name()
        target_dir.mkdir(parents=True, exist_ok=True)

        if USE_POSTGRES:
            db_result = backup_postgres(target_dir)
        else:
            db_result = backup_sqlite(target_dir)

        img_result = backup_images(target_dir)
        cleanup_old_backups()

        return {
            "success": True,
            "backup_folder": str(target_dir),
            "database": db_result,
            "images": img_result
        }

    except Exception as e:
        log_error("run_daily_backup", str(e))
        return {
            "success": False,
            "error": str(e)
        }


def list_backups():
    try:
        items = []
        for folder in BACKUP_FOLDER.iterdir():
            if folder.is_dir() and folder.name.startswith("backup_"):
                items.append({
                    "name": folder.name,
                    "path": str(folder),
                    "created_at": datetime.fromtimestamp(folder.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "size": folder_size(folder)
                })

        items.sort(key=lambda x: x["created_at"], reverse=True)
        return {"success": True, "files": items}

    except Exception as e:
        log_error("list_backups", str(e))
        return {"success": False, "files": []}
