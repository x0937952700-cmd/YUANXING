from flask import Flask, request, jsonify, render_template
import psycopg2, os, cv2, numpy as np, re
from PIL import Image
import pytesseract

app = Flask(__name__, template_folder="templates", static_folder="static")
DB = os.environ.get("DATABASE_URL")

def conn():
    return psycopg2.connect(DB, sslmode='require')

def init():
    c=conn();cur=c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory(
        product TEXT PRIMARY KEY,
        qty INT,
        location TEXT,
        customer TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs(
        id SERIAL PRIMARY KEY,
        action TEXT,
        t TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.commit();c.close()

init()

# ===== OCR =====
@app.route("/api/upload_ocr", methods=["POST"])
def upload_ocr():
    file=request.files["file"]
    img=np.array(Image.open(file.stream).convert("RGB"))
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    text=pytesseract.image_to_string(gray,lang='chi_tra+eng')
    lines=[l.strip() for l in text.splitlines() if l.strip()]
    return {"text":text,"lines":lines}

# ===== 入庫 =====
@app.route("/api/add", methods=["POST"])
def add():
    d=request.json
    c=conn();cur=c.cursor()

    cur.execute("SELECT qty FROM inventory WHERE product=%s",(d["p"],))
    r=cur.fetchone()

    if r:
        cur.execute("UPDATE inventory SET qty=qty+%s WHERE product=%s",(d["q"],d["p"]))
    else:
        cur.execute("INSERT INTO inventory VALUES(%s,%s,'','')",(d["p"],d["q"]))

    cur.execute("INSERT INTO logs(action) VALUES(%s)",(f"入庫 {d['p']}",))
    c.commit();c.close()
    return {"ok":1}

# ===== 庫存 =====
@app.route("/api/inventory")
def inventory():
    c=conn();cur=c.cursor()
    cur.execute("SELECT product,qty FROM inventory")
    d=cur.fetchall()
    c.close()
    return {"items":[{"p":i[0],"q":i[1]} for i in d]}

# ===== 訂單 =====
@app.route("/api/order", methods=["POST"])
def order():
    d=request.json
    c=conn();cur=c.cursor()

    cur.execute("SELECT qty FROM inventory WHERE product=%s",(d["p"],))
    r=cur.fetchone()

    if not r or r[0]<d["q"]:
        return {"error":"庫存不足"}

    cur.execute("UPDATE inventory SET qty=qty-%s WHERE product=%s",(d["q"],d["p"]))
    cur.execute("INSERT INTO logs(action) VALUES(%s)",(f"訂單 {d['p']}",))
    c.commit();c.close()
    return {"ok":1}

# ===== 出貨 =====
@app.route("/api/ship", methods=["POST"])
def ship():
    d=request.json
    c=conn();cur=c.cursor()

    cur.execute("SELECT qty FROM inventory WHERE product=%s",(d["p"],))
    r=cur.fetchone()

    if not r or r[0]<d["q"]:
        return {"error":"庫存不足"}

    cur.execute("UPDATE inventory SET qty=qty-%s WHERE product=%s",(d["q"],d["p"]))
    cur.execute("INSERT INTO logs(action) VALUES(%s)",(f"出貨 {d['p']}",))
    c.commit();c.close()
    return {"ok":1}

# ===== 出貨查詢 =====
@app.route("/api/orders")
def orders():
    c=conn();cur=c.cursor()
    cur.execute("SELECT action,t FROM logs WHERE action LIKE '出貨%'")
    d=cur.fetchall()
    c.close()
    return {"items":[{"product":i[0],"qty":1} for i in d]}

# ===== 倉庫 =====
@app.route("/api/w")
def w():
    c=conn();cur=c.cursor()
    cur.execute("SELECT product,qty,location FROM inventory")
    d=cur.fetchall()
    c.close()
    return jsonify(d)

# ===== 拖拉 =====
@app.route("/api/move", methods=["POST"])
def move():
    d=request.json
    c=conn();cur=c.cursor()
    cur.execute("UPDATE inventory SET location=%s WHERE product=%s",(d["l"],d["p"]))
    cur.execute("INSERT INTO logs(action) VALUES(%s)",(f"移動 {d['p']}",))
    c.commit();c.close()
    return {"ok":1}

# ===== 客戶 =====
@app.route("/api/customers")
def customers():
    return {"items":[{"name":"客戶A"},{"name":"客戶B"}]}

# ===== 異動 =====
@app.route("/api/activity")
def activity():
    c=conn();cur=c.cursor()
    cur.execute("SELECT action,t FROM logs ORDER BY id DESC LIMIT 50")
    d=cur.fetchall()
    c.close()
    return {"items":[{"user":"系統","action":i[0],"t":str(i[1])} for i in d]}

@app.route("/")
def home():
    return render_template("index.html")

@app.after_request
def no_cache(res):
    res.headers["Cache-Control"]="no-store"
    return res

app.run(host="0.0.0.0",port=10000)
