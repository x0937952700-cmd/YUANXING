from flask import Flask, request, jsonify, render_template
import psycopg2, os

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ===== 初始化 =====
def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'user',
        is_blocked BOOLEAN DEFAULT FALSE
    )
    """)

    # 預設管理員
    c.execute("""
    INSERT INTO users (username,password,role)
    VALUES ('陳韋廷','1234','admin')
    ON CONFLICT (username) DO NOTHING
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
        # 自動建立員工
        c.execute("INSERT INTO users(username,password) VALUES(%s,%s)",(u,p))
        conn.commit()
        return jsonify({"success":True,"role":"user"})

# ===== 取得員工 =====
@app.route("/api/users")
def get_users():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT username,role,is_blocked FROM users ORDER BY role DESC, username")
    rows = c.fetchall()

    data = []
    for r in rows:
        data.append({
            "username":r[0],
            "role":r[1],
            "is_blocked":r[2]
        })

    return jsonify(data)

# ===== 封鎖 =====
@app.route("/api/block", methods=["POST"])
def block():
    data = request.json
    target = data["username"]

    conn = get_conn()
    c = conn.cursor()

    # 禁止封鎖管理員
    c.execute("SELECT role FROM users WHERE username=%s",(target,))
    role = c.fetchone()

    if role and role[0] == "admin":
        return jsonify({"error":"不能封鎖管理員"})

    c.execute("UPDATE users SET is_blocked=TRUE WHERE username=%s",(target,))
    conn.commit()

    return jsonify({"success":True})

# ===== 解封 =====
@app.route("/api/unblock", methods=["POST"])
def unblock():
    data = request.json
    target = data["username"]

    conn = get_conn()
    c = conn.cursor()

    c.execute("UPDATE users SET is_blocked=FALSE WHERE username=%s",(target,))
    conn.commit()

    return jsonify({"success":True})

@app.route("/")
def home():
    return render_template("base.html")

if __name__ == "__main__":
    app.run(debug=True)