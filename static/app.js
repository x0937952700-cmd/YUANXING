from flask import Flask, request, jsonify, render_template, session
import psycopg2, os, cv2, numpy as np, re
from PIL import Image
import pytesseract
from datetime import datetime

app = Flask(__name__)
app.secret_key = "admin123"
DB = os.environ.get("DATABASE_URL")

# ===== DB =====
def conn():
    return psycopg2.connect(DB, sslmode='require')

def init():
    c=conn(); cur=c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        username TEXT PRIMARY KEY,
        password TEXT,
        role TEXT
    )
    """)

    cur.execute("""
    INSERT INTO users VALUES('陳韋廷','1234','admin')
    ON CONFLICT DO NOTHING
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS inventory(
        product TEXT PRIMARY KEY,
        qty INT,
        location TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs(
        id SERIAL PRIMARY KEY,
        user_name TEXT,
        action TEXT,
        t TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.commit(); c.close()

init()

# ===== 登入 =====
@app.route("/api/login", methods=["POST"])
def login():
    d=request.json
    c=conn(); cur=c.cursor()
    cur.execute("SELECT role FROM users WHERE username=%s AND password=%s",
                (d["u"],d["p"]))
    r=cur.fetchone()
    c.close()

    if not r:
        return {"error":"登入失敗"}

    session["user"]=d["u"]
    session["role"]=r[0]

    return {"ok":1,"role":r[0]}

@app.route("/api/me")
def me():
    return {
        "user":session.get("user"),
        "role":session.get("role")
    }

# ===== OCR =====
def preprocess(img):
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    gray=cv2.equalizeHist(gray)
    _,th=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    return th

def ocr(img):
    return pytesseract.image_to_string(img,lang='chi_tra+eng')

# ===== 自動入庫 =====
@app.route("/api/auto", methods=["POST"])
def auto():
    if "user" not in session:
        return {"error":"未登入"}

    file=request.files["file"]
    img=np.array(Image.open(file.stream))
    img=preprocess(img)

    text=ocr(img)
    lines=[l for l in text.splitlines() if l.strip()]

    c=conn(); cur=c.cursor()

    for l in lines:
        q=int(re.findall(r'\d+',l)[-1]) if re.findall(r'\d+',l) else 1

        cur.execute("SELECT qty FROM inventory WHERE product=%s",(l,))
        r=cur.fetchone()

        if r:
            cur.execute("UPDATE inventory SET qty=qty+%s WHERE product=%s",(q,l))
        else:
            cur.execute("INSERT INTO inventory VALUES(%s,%s,'A-1')",(l,q))

        cur.execute("INSERT INTO logs(user_name,action) VALUES(%s,%s)",
                    (session["user"],f"入庫 {l}"))

    c.commit(); c.close()

    return {"ok":1}

# ===== 即時資料 =====
@app.route("/api/inventory")
def inv():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT * FROM inventory")
    d=cur.fetchall()
    c.close()
    return {"items":d}

# ===== 異動 =====
@app.route("/api/activity")
def act():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT user_name,action,t FROM logs ORDER BY id DESC LIMIT 20")
    d=cur.fetchall()
    c.close()
    return {"items":d}

# ===== 關閉快取 =====
@app.after_request
def no_cache(res):
    res.headers["Cache-Control"]="no-store,no-cache,must-revalidate"
    return res

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)