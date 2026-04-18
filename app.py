from flask import Flask, request, jsonify, render_template
import psycopg2, os, cv2, numpy as np
from PIL import Image
import pytesseract
import easyocr

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
    CREATE TABLE IF NOT EXISTS orders(
        id SERIAL PRIMARY KEY,
        product TEXT,
        qty INT,
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

# ===== OCR =====
reader = easyocr.Reader(['ch_tra','en'], gpu=False)

def read_img(file):
    img = Image.open(file.stream).convert("RGB")
    return np.array(img)

def auto_crop(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray,50,150)
    cnts,_ = cv2.findContours(edges,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if cnts:
        c = max(cnts, key=cv2.contourArea)
        x,y,w,h = cv2.boundingRect(c)
        return img[y:y+h,x:x+w]
    return img

def ocr_tesseract(img):
    text = pytesseract.image_to_string(img, lang='chi_tra+eng')
    return text, 0.6

def ocr_easy(img):
    res = reader.readtext(img)
    text = "\n".join([r[1] for r in res])
    conf = float(np.mean([r[2] for r in res])) if res else 0.0
    return text, conf

def apply_fix(text):
    c=conn(); cur=c.cursor()
    cur.execute("SELECT wrong,correct FROM ocr_fix ORDER BY count DESC")
    for w,corr in cur.fetchall():
        if w in text:
            text = text.replace(w,corr)
    text = text.replace('O','0').replace('l','1')
    c.close()
    return text

@app.route("/api/upload_ocr", methods=["POST"])
def upload_ocr():
    file = request.files["file"]
    img = auto_crop(read_img(file))

    t1,c1 = ocr_tesseract(img)
    t2,c2 = ocr_easy(img)

    text,conf = (t2,c2) if c2>c1 else (t1,c1)

    text = apply_fix(text)
    lines = [i.strip() for i in text.splitlines() if i.strip()]

    return jsonify({
        "text": text,
        "lines": lines,
        "confidence": conf
    })

@app.route("/api/ocr_learn", methods=["POST"])
def learn():
    d=request.json
    c=conn(); cur=c.cursor()
    cur.execute("""
    INSERT INTO ocr_fix(wrong,correct,count)
    VALUES(%s,%s,1)
    ON CONFLICT (wrong)
    DO UPDATE SET correct=%s, count=ocr_fix.count+1
    """,(d["w"],d["c"],d["c"]))
    c.commit(); c.close()
    return {"ok":1}

# ===== 首頁 =====
@app.route("/")
def home():
    return render_template("index.html")

# ===== 庫存 =====
@app.route("/api/inventory")
def inventory():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT * FROM inventory")
    d=cur.fetchall(); c.close()
    return jsonify({"items":[{"p":i[0],"q":i[1],"l":i[2],"c":i[3]} for i in d]})

@app.route("/api/add", methods=["POST"])
def add():
    d=request.json
    c=conn(); cur=c.cursor()

    cur.execute("SELECT qty FROM inventory WHERE product=%s",(d["p"],))
    r=cur.fetchone()

    if r:
        cur.execute("UPDATE inventory SET qty=qty+%s WHERE product=%s",(d["q"],d["p"]))
    else:
        cur.execute("INSERT INTO inventory VALUES(%s,%s,'',%s)",
                    (d["p"],d["q"],d.get("c","")))

    cur.execute("INSERT INTO logs(action) VALUES(%s)",("入庫 "+d["p"],))
    c.commit(); c.close()
    return {"ok":1}

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
    cur.execute("INSERT INTO orders(product,qty,customer) VALUES(%s,%s,%s)",
                (d["p"],d["q"],d.get("c","")))

    cur.execute("INSERT INTO logs(action) VALUES(%s)",("訂單 "+d["p"],))
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
    cur.execute("INSERT INTO logs(action) VALUES(%s)",("出貨 "+d["p"],))
    c.commit(); c.close()
    return {"ok":1}

# ===== 倉庫拖拉 =====
@app.route("/api/move", methods=["POST"])
def move():
    d=request.json
    c=conn(); cur=c.cursor()
    cur.execute("UPDATE inventory SET location=%s WHERE product=%s",(d["l"],d["p"]))
    cur.execute("INSERT INTO logs(action) VALUES(%s)",("移動 "+d["p"],))
    c.commit(); c.close()
    return {"ok":1}

@app.route("/api/w")
def w():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT product,qty,location FROM inventory")
    d=cur.fetchall(); c.close()
    return jsonify(d)

# ===== 異動 =====
@app.route("/api/activity")
def act():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT action,t FROM logs ORDER BY id DESC LIMIT 50")
    d=cur.fetchall(); c.close()
    return {"items":[{"a":i[0],"t":str(i[1])} for i in d]}

# ===== 完全關閉快取（關鍵）=====
@app.after_request
def no_cache(res):
    res.headers["Cache-Control"]="no-store,no-cache,must-revalidate,max-age=0"
    res.headers["Pragma"]="no-cache"
    res.headers["Expires"]="0"
    return res

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)