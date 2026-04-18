from flask import Flask, request, jsonify, render_template
import psycopg2, os, datetime

app = Flask(__name__)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

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

    c.execute("""
    CREATE TABLE IF NOT EXISTS inventory(
        product TEXT PRIMARY KEY,
        qty INT,
        location TEXT,
        customer TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS logs(
        id SERIAL PRIMARY KEY,
        action TEXT,
        user_name TEXT,
        time TEXT
    )
    """)

    c.execute("""
    INSERT INTO users (username,password,role)
    VALUES ('陳韋廷','1234','admin')
    ON CONFLICT (username) DO UPDATE SET role='admin'
    """)

    conn.commit()
    conn.close()

init_db()

@app.route("/")
def home():
    return render_template("index.html")

# ===== 登入 =====
@app.route("/api/login", methods=["POST"])
def login():
    d = request.json
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT password,role,is_blocked FROM users WHERE username=%s",(d["u"],))
    r = c.fetchone()

    if r:
        if r[2]: return jsonify({"error":"封鎖"})
        if r[0]!=d["p"]: return jsonify({"error":"錯誤"})
        return jsonify({"ok":1,"role":r[1]})
    else:
        c.execute("INSERT INTO users(username,password) VALUES(%s,%s)",(d["u"],d["p"]))
        conn.commit()
        return jsonify({"ok":1,"role":"user"})

# ===== 入庫（合併庫存）=====
@app.route("/api/add", methods=["POST"])
def add():
    d = request.json
    conn = get_conn()
    c = conn.cursor()

    # 有就累加
    c.execute("SELECT qty FROM inventory WHERE product=%s",(d["p"],))
    r = c.fetchone()

    if r:
        c.execute("UPDATE inventory SET qty=qty+%s WHERE product=%s",(d["q"],d["p"]))
    else:
        c.execute("INSERT INTO inventory(product,qty,location,customer) VALUES(%s,%s,%s,%s)",
                  (d["p"],d["q"],d.get("loc",""),d.get("c","")))

    c.execute("INSERT INTO logs(action,user_name,time) VALUES(%s,%s,%s)",
              ("入庫:"+d["p"],d["user"],str(datetime.datetime.now())))

    conn.commit()
    return jsonify({"ok":1})

# ===== 出貨（鎖庫存）=====
@app.route("/api/ship", methods=["POST"])
def ship():
    d = request.json
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT qty FROM inventory WHERE product=%s FOR UPDATE",(d["p"],))
    r = c.fetchone()

    if not r or r[0] < d["q"]:
        return jsonify({"error":"庫存不足"})

    c.execute("UPDATE inventory SET qty=qty-%s WHERE product=%s",(d["q"],d["p"]))

    c.execute("INSERT INTO logs(action,user_name,time) VALUES(%s,%s,%s)",
              ("出貨:"+d["p"],d["user"],str(datetime.datetime.now())))

    conn.commit()
    return jsonify({"ok":1})

# ===== 倉庫 =====
@app.route("/api/warehouse")
def warehouse():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT product,qty,location FROM inventory")
    rows = c.fetchall()

    return jsonify([{"p":r[0],"q":r[1],"l":r[2]} for r in rows])

# ===== logs =====
@app.route("/api/logs")
def logs():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT action,user_name,time FROM logs ORDER BY id DESC LIMIT 50")
    rows = c.fetchall()

    return jsonify([{"a":r[0],"u":r[1],"t":r[2]} for r in rows])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
