from flask import Flask, request, jsonify, render_template
import psycopg2, os, cv2, numpy as np
from PIL import Image
import pytesseract
import easyocr

app = Flask(__name__, template_folder="templates", static_folder="static")

DB = os.environ.get("DATABASE_URL")

def conn():
    return psycopg2.connect(DB, sslmode='require')

# ===== 初始化 =====
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
        w TEXT PRIMARY KEY,
        c TEXT
    )
    """)

    c.commit()
    c.close()

init()

# ===== OCR =====
reader = easyocr.Reader(['ch_tra','en'], gpu=False)

def read_img(file):
    img = Image.open(file.stream).convert("RGB")
    return np.array(img)

def auto_crop(img):
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray,50,150)
        cnts,_ = cv2.findContours(edges,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            c = max(cnts, key=cv2.contourArea)
            x,y,w,h = cv2.boundingRect(c)
            return img[y:y+h,x:x+w]
    except:
        pass
    return img

def ocr_tesseract(img):
    try:
        text = pytesseract.image_to_string(img)
        return text, 0.6
    except:
        return "", 0

def ocr_easy(img):
    try:
        res = reader.readtext(img)
        text = "\n".join([r[1] for r in res])
        conf = float(np.mean([r[2] for r in res])) if res else 0
        return text, conf
    except:
        return "", 0

def apply_fix(t):
    c=conn(); cur=c.cursor()
    cur.execute("SELECT w,c FROM ocr_fix")
    for w,corr in cur.fetchall():
        t = t.replace(w, corr)
    c.close()

    return t.replace('l','1').replace('O','0')

def parse_lines(t):
    return [s.strip() for s in t.splitlines() if s.strip()]

# ===== OCR API =====
@app.route("/api/upload_ocr", methods=["POST"])
def upload_ocr():

    if "file" not in request.files:
        return jsonify({"error":"沒有檔案"})

    file = request.files["file"]

    img = read_img(file)
    img = auto_crop(img)

    text, conf = ocr_tesseract(img)

    if conf < 0.7:
        t2, c2 = ocr_easy(img)
        if c2 > conf:
            text, conf = t2, c2

    text = apply_fix(text)
    lines = parse_lines(text)

    return jsonify({
        "text": text,
        "lines": lines,
        "confidence": conf
    })

# ===== 學習 =====
@app.route("/api/ocr_learn", methods=["POST"])
def learn():
    d=request.json
    c=conn(); cur=c.cursor()

    cur.execute("""
    INSERT INTO ocr_fix(w,c) VALUES(%s,%s)
    ON CONFLICT (w) DO UPDATE SET c=%s
    """,(d["w"],d["c"],d["c"]))

    c.commit()
    c.close()
    return {"ok":1}

# ===== 首頁 =====
@app.route("/")
def home():
    return render_template("index.html")

# ===== 庫存 =====
@app.route("/api/inventory")
def inventory():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT product,qty,location,customer FROM inventory")
    data=cur.fetchall()
    c.close()

    return {"items":[{"p":i[0],"q":i[1],"l":i[2],"c":i[3]} for i in data]}

# ===== 入庫 =====
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
                    (d["p"],d["q"], d.get("c","")))

    cur.execute("INSERT INTO logs(action) VALUES(%s)",("入庫 "+d["p"],))

    c.commit()
    c.close()
    return {"ok":1}

# ===== 移動 =====
@app.route("/api/move", methods=["POST"])
def move():
    d=request.json
    c=conn(); cur=c.cursor()

    cur.execute("UPDATE inventory SET location=%s WHERE product=%s",(d["l"],d["p"]))

    c.commit()
    c.close()
    return {"ok":1}

# ===== 異動 =====
@app.route("/api/activity")
def act():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT action,t FROM logs ORDER BY id DESC LIMIT 20")
    data=cur.fetchall()
    c.close()

    return {"items":[{"a":i[0],"t":str(i[1])} for i in data]}

# ===== 關閉快取 =====
@app.after_request
def no_cache(res):
    res.headers["Cache-Control"]="no-store,no-cache,must-revalidate"
    return res

# ===== 啟動 =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)