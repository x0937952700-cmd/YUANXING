
import os, json, shutil
from datetime import datetime
from db import get_db, USE_POSTGRES, DATABASE_URL, log_error

BACKUP_FOLDER = "backups"
os.makedirs(BACKUP_FOLDER, exist_ok=True)

def backup_filename(prefix, ext):
    return os.path.join(BACKUP_FOLDER, f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}")

def cleanup_backups(prefix, keep=7):
    try:
        files = []
        for name in os.listdir(BACKUP_FOLDER):
            path = os.path.join(BACKUP_FOLDER, name)
            if os.path.isfile(path) and name.startswith(prefix):
                files.append((os.path.getmtime(path), path))
        files.sort(reverse=True)
        for _, path in files[keep:]:
            try:
                os.remove(path)
            except Exception:
                pass
    except Exception as e:
        log_error("cleanup_backups", str(e))

def backup_sqlite():
    try:
        db_path = DATABASE_URL.replace("sqlite:///", "")
        target = backup_filename("sqlite_backup", "db")
        shutil.copy2(db_path, target)
        cleanup_backups("sqlite_backup", 7)
        return {"success": True, "type": "sqlite", "file": target}
    except Exception as e:
        log_error("backup_sqlite", str(e))
        return {"success": False, "error": str(e)}

def backup_postgres():
    try:
        conn = get_db()
        cur = conn.cursor()
        tables = ["users","inventory","orders","master_orders","shipping_records","corrections","image_hashes","logs","errors","customers","warehouse_slots","settings"]
        data = {}
        for table in tables:
            cur.execute(f"SELECT * FROM {table}")
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
            data[table] = [dict(zip(columns, row)) for row in rows]
        conn.close()
        target = backup_filename("postgres_backup", "json")
        with open(target, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        cleanup_backups("postgres_backup", 7)
        return {"success": True, "type": "postgres", "file": target}
    except Exception as e:
        log_error("backup_postgres", str(e))
        return {"success": False, "error": str(e)}

def backup_uploads():
    try:
        target = os.path.join(BACKUP_FOLDER, datetime.now().strftime("uploads_%Y%m%d_%H%M%S"))
        os.makedirs(target, exist_ok=True)
        if os.path.isdir("uploads"):
            for name in os.listdir("uploads"):
                if name == ".gitkeep":
                    continue
                src = os.path.join("uploads", name)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(target, name))
        cleanup_backups("uploads_", 7)
        return {"success": True, "type": "uploads", "file": target}
    except Exception as e:
        log_error("backup_uploads", str(e))
        return {"success": False, "error": str(e)}

def run_daily_backup():
    try:
        db_result = backup_postgres() if USE_POSTGRES else backup_sqlite()
        up_result = backup_uploads()
        return {"success": db_result.get("success", False) and up_result.get("success", False), "database": db_result, "uploads": up_result}
    except Exception as e:
        log_error("run_daily_backup", str(e))
        return {"success": False, "error": str(e)}

def list_backups():
    try:
        files = []
        for name in os.listdir(BACKUP_FOLDER):
            path = os.path.join(BACKUP_FOLDER, name)
            if os.path.isfile(path):
                files.append({"filename": name, "size": os.path.getsize(path), "created_at": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")})
        files.sort(key=lambda x: x["created_at"], reverse=True)
        return {"success": True, "files": files}
    except Exception as e:
        log_error("list_backups", str(e))
        return {"success": False, "files": []}
