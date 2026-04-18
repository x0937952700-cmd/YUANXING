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
    CREATE TABLE IF NOT EXISTS inventory(
        id SERIAL PRIMARY KEY,
        product TEXT,
        qty INT,
        location TEXT,
        customer TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id SERIAL PRIMARY KEY,
        product TEXT,
        qty INT,
        customer TEXT,
        status TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS logs(
        id SERIAL PRIMARY KEY,
        action TEXT,
        time TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

@app.route("/")
def home():
    return render_template("index.html")

# ===== OCR =====
@app.route("/upload", methods=["POST"])
def upload():
    return jsonify({"text":"130x30x05","confidence":0.9})

# ===== 入庫 =====
@app.route("/add", methods=["POST"])
def add():
    text = request.form["text"]

    conn = get_conn()
    c = conn.cursor()

    c.execute("INSERT INTO inventory(product,qty) VALUES(%s,%s)",(text,1))
    c.execute("INSERT INTO logs(action,time) VALUES(%s,%s)",
              ("入庫:"+text,str(datetime.datetime.now())))

    conn.commit()
    conn.close()

    return "OK"

# ===== 訂單 =====
@app.route("/api/order", methods=["POST"])
def order():
    data = request.json

    conn = get_conn()
    c = conn.cursor()

    c.execute("INSERT INTO orders(product,qty,customer,status) VALUES(%s,%s,%s,%s)",
              (data["product"],data["qty"],data["customer"],"pending"))

    conn.commit()
    conn.close()

    return jsonify({"ok":True})

# ===== 出貨 =====
@app.route("/api/ship", methods=["POST"])
def ship():
    data = request.json

    conn = get_conn()
    c = conn.cursor()

    # 防超賣
    c.execute("SELECT qty FROM inventory WHERE product=%s",(data["product"],))
    row = c.fetchone()

    if not row or row[0] < data["qty"]:
        return jsonify({"error":"庫存不足"})

    c.execute("UPDATE inventory SET qty=qty-%s WHERE product=%s",
              (data["qty"],data["product"]))

    c.execute("INSERT INTO logs(action,time) VALUES(%s,%s)",
              ("出貨:"+data["product"],str(datetime.datetime.now())))

    conn.commit()
    conn.close()

    return jsonify({"ok":True})

# ===== 倉庫 =====
@app.route("/api/warehouse")
def warehouse():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT location,product,qty,customer FROM inventory")
    rows = c.fetchall()

    return jsonify([
        {"location":r[0],"product":r[1],"qty":r[2],"customer":r[3]}
        for r in rows
    ])

# ===== 搜尋 =====
@app.route("/api/search")
def search():
    kw = request.args.get("kw")

    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT location FROM inventory WHERE product ILIKE %s",
              ("%"+kw+"%",))

    rows = c.fetchall()

    return jsonify([{"location":r[0]} for r in rows])

# ===== logs =====
@app.route("/api/logs")
def logs():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT action,time FROM logs ORDER BY id DESC LIMIT 20")
    rows = c.fetchall()

    return jsonify([{"action":r[0],"time":r[1]} for r in rows])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
