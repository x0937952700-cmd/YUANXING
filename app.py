from flask import Flask, request, jsonify, render_template
import psycopg2, os

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# ===== 初始化 + 自動修復 =====
def init_db():
    conn = get_conn()
    c = conn.cursor()

    # 建表（舊的會保留）
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'user',
        is_blocked BOOLEAN DEFAULT FALSE
    )
    """)

    # 🔥 補欄位（關鍵）
    try:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
    except:
        pass

    try:
        c.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT FALSE")
    except:
        pass

    # 設定預設管理員
    c.execute("""
    INSERT INTO users (username,password,role)
    VALUES ('陳韋廷','1234','admin')
    ON CONFLICT (username) DO UPDATE SET role='admin'
    """)

    conn.commit()
    conn.close()

init_db()

# ===== 登入 =====
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    u = data["username"]
    p = data["password"]

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT password,role,is_blocked FROM users WHERE username=%s",(u,))
    row = c.fetchone()

    if row:
        if row[2]:
            return jsonify({"error":"此帳號已被封鎖"})
        if row[0] != p:
            return jsonify({"error":"密碼錯誤"})
        return jsonify({"success":True,"role":row[1]})
    else:
        c.execute("INSERT INTO users(username,password) VALUES(%s,%s)",(u,p))
        conn.commit()
        return jsonify({"success":True,"role":"user"})

# ===== 員工列表 =====
@app.route("/api/users")
def users():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT username,role,is_blocked FROM users ORDER BY role DESC")
    rows = c.fetchall()

    return jsonify([
        {"username":r[0],"role":r[1],"is_blocked":r[2]}
        for r in rows
    ])

# ===== 封鎖 =====
@app.route("/api/block", methods=["POST"])
def block():
    user = request.json["username"]

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT role FROM users WHERE username=%s",(user,))
    r = c.fetchone()

    if r and r[0] == "admin":
        return jsonify({"error":"不能封鎖管理員"})

    c.execute("UPDATE users SET is_blocked=TRUE WHERE username=%s",(user,))
    conn.commit()

    return jsonify({"success":True})

# ===== 解封 =====
@app.route("/api/unblock", methods=["POST"])
def unblock():
    user = request.json["username"]

    conn = get_conn()
    c = conn.cursor()

    c.execute("UPDATE users SET is_blocked=FALSE WHERE username=%s",(user,))
    conn.commit()

    return jsonify({"success":True})

@app.route("/")
def home():
    return "系統正常運作 ✅"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
