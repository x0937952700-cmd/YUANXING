from flask import Flask, request, jsonify, render_template
import psycopg2, os, cv2, numpy as np, re
from PIL import Image
import pytesseract

app = Flask(__name__, template_folder="templates", static_folder="static")
DB = os.environ.get("DATABASE_URL")

# ===== DB =====
def conn():
    return psycopg2.connect(DB, sslmode='require')

def init():
    c=conn(); cur=c.cursor()

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

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ocr_fix(
        wrong TEXT PRIMARY KEY,
        correct TEXT,
        count INT DEFAULT 1
    )
    """)

    c.commit(); c.close()

init()

# ================= OCR =================

def read_img(file):
    img = Image.open(file.stream).convert("RGB")
    return np.array(img)

def preprocess(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    blur = cv2.GaussianBlur(gray,(3,3),0)
    _,th = cv2.threshold(blur,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    return th

def ocr(img):
    configs = ["--oem 3 --psm 6","--oem 3 --psm 7","--oem 3 --psm 11"]
    texts = []
    for c in configs:
        t = pytesseract.image_to_string(img, lang='chi_tra+eng', config=c)
        if t.strip():
            texts.append(t)
    return max(texts, key=len) if texts else ""

def apply_fix(text):
    c=conn(); cur=c.cursor()
    cur.execute("SELECT wrong,correct FROM ocr_fix ORDER BY count DESC")
    for w,corr in cur.fetchall():
        text = text.replace(w,corr)
    c.close()
    return text.replace('O','0').replace('l','1')

def parse_lines(text):
    lines = [i.strip() for i in text.splitlines() if i.strip()]
    result = []
    for l in lines:
        qty = re.findall(r'\d+', l)
        result.append({
            "product": l,
            "qty": int(qty[-1]) if qty else 1
        })
    return result

# ===== OCR（不自動入庫）=====
@app.route("/api/upload_ocr", methods=["POST"])
def upload_ocr():
    file = request.files["file"]
    img = preprocess(read_img(file))
    text = apply_fix(ocr(img))
    parsed = parse_lines(text)

    return jsonify({
        "text": text,
        "lines": [i["product"] for i in parsed],
        "parsed": parsed
    })

# ================= 核心功能 =================

def auto_location():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT location FROM inventory")
    used = [i[0] for i in cur.fetchall()]
    c.close()

    for i in range(1,200):
        loc = f"A-{i}"
        if loc not in used:
            return loc
    return "A-0"

# ===== 入庫（手動）=====
@app.route("/api/add", methods=["POST"])
def add():
    d=request.json
    c=conn(); cur=c.cursor()

    cur.execute("SELECT qty FROM inventory WHERE product=%s",(d["p"],))
    r=cur.fetchone()

    if r:
        cur.execute("UPDATE inventory SET qty=qty+%s WHERE product=%s",(d["q"],d["p"]))
    else:
        loc = auto_location()
        cur.execute("INSERT INTO inventory VALUES(%s,%s,%s,'')",(d["p"],d["q"],loc))

    cur.execute("INSERT INTO logs(action) VALUES(%s)",(f"入庫 {d['p']}",))
    c.commit(); c.close()
    return {"ok":1}

# ===== 庫存 =====
@app.route("/api/inventory")
def inventory():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT product,qty,location FROM inventory")
    d=cur.fetchall()
    c.close()
    return {"items":[{"p":i[0],"q":i[1],"l":i[2]} for i in d]}

# ===== 訂單（防超賣）=====
@app.route("/api/order", methods=["POST"])
def order():
    d=request.json
    c=conn(); cur=c.cursor()

    cur.execute("SELECT qty FROM inventory WHERE product=%s",(d["p"],))
    r=cur.fetchone()

    if not r or r[0] < d["q"]:
        return {"error":"庫存不足"}

    cur.execute("UPDATE inventory SET qty=qty-%s WHERE product=%s",(d["q"],d["p"]))
    cur.execute("INSERT INTO logs(action) VALUES(%s)",(f"訂單 {d['p']}",))

    c.commit(); c.close()
    return {"ok":1}

# ===== 出貨 =====
@app.route("/api/ship", methods=["POST"])
def ship():
    d=request.json
    c=conn(); cur=c.cursor()

    cur.execute("SELECT qty FROM inventory WHERE product=%s",(d["p"],))
    r=cur.fetchone()

    if not r or r[0] < d["q"]:
        return {"error":"庫存不足"}

    cur.execute("UPDATE inventory SET qty=qty-%s WHERE product=%s",(d["q"],d["p"]))
    cur.execute("INSERT INTO logs(action) VALUES(%s)",(f"出貨 {d['p']}",))

    c.commit(); c.close()
    return {"ok":1}

# ===== 出貨查詢 =====
@app.route("/api/orders")
def orders():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT action,t FROM logs WHERE action LIKE '出貨%' ORDER BY id DESC")
    d=cur.fetchall()
    c.close()
    return {"items":[{"product":i[0],"time":str(i[1])} for i in d]}

# ===== 倉庫 =====
@app.route("/api/w")
def w():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT product,qty,location FROM inventory")
    d=cur.fetchall()
    c.close()
    return d

# ===== 拖拉 =====
@app.route("/api/move", methods=["POST"])
def move():
    d=request.json
    c=conn(); cur=c.cursor()

    cur.execute("UPDATE inventory SET location=%s WHERE product=%s",(d["l"],d["p"]))
    cur.execute("INSERT INTO logs(action) VALUES(%s)",(f"移動 {d['p']}",))

    c.commit(); c.close()
    return {"ok":1}

# ===== 客戶 =====
@app.route("/api/customers")
def customers():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT DISTINCT customer FROM inventory WHERE customer!=''")
    d=cur.fetchall()
    c.close()
    return {"items":[{"name":i[0]} for i in d]}

# ===== 異動 =====
@app.route("/api/activity")
def activity():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT action,t FROM logs ORDER BY id DESC LIMIT 50")
    d=cur.fetchall()
    c.close()
    return {"items":[{"action":i[0],"t":str(i[1])} for i in d]}

# ===== 首頁 =====
@app.route("/")
def home():
    return render_template("index.html")

# ===== 關閉快取 =====
@app.after_request
def no_cache(res):
    res.headers["Cache-Control"]="no-store,no-cache,must-revalidate,max-age=0"
    res.headers["Pragma"]="no-cache"
    res.headers["Expires"]="0"
    return res

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)