from flask import Flask, request, jsonify, render_template
import psycopg2, os

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# ===== 初始化 DB =====
def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id SERIAL PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    c.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name='users'
    """)
    cols = [r[0] for r in c.fetchall()]

    if "role" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")

    if "is_blocked" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT FALSE")

    c.execute("""
    INSERT INTO users (username,password,role)
    VALUES ('陳韋廷','1234','admin')
    ON CONFLICT (username)
    DO UPDATE SET role='admin'
    """)

    conn.commit()
    conn.close()

init_db()

# ===== 首頁（這才是關鍵）=====
@app.route("/")
def home():
    return render_template("home.html")   # ← 改這裡！

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)