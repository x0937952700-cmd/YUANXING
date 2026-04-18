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

# ===== OCR強化 =====

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
    configs = [
        "--oem 3 --psm 6",
        "--oem 3 --psm 7",
        "--oem 3 --psm 11"
    ]

    texts = []
    for c in configs:
        t = pytesseract.image_to_string(img, lang='chi_tra+eng', config=c)
        if t.strip():
            texts.append(t)

    best = max(texts, key=len) if texts else ""
    return best

def apply_fix(text):
    c=conn(); cur=c.cursor()
    cur.execute("SELECT wrong,correct FROM ocr_fix ORDER BY count DESC")
    for w,corr in cur.fetchall():
        text = text.replace(w,corr)
    text = text.replace('O','0').replace('l','1')
    c.close()
    return text

# ===== 解析 =====

def parse_lines(text):
    lines = [i.strip() for i in text.splitlines() if i.strip()]
    result = []

    for l in lines:
        size = re.findall(r'\d+[xX×]\d+', l)
        qty = re.findall(r'\d+', l)

        result.append({
            "product": l,
            "size": size[0] if size else "",
            "qty": int(qty[-1]) if qty else 1
        })

    return result

# ===== 自動分配倉庫格位 =====

def auto_location():
    c=conn(); cur=c.cursor()

    # 找目前最大位置
    cur.execute("SELECT location FROM inventory WHERE location!=''")
    used = [i[0] for i in cur.fetchall()]

    for i in range(1,100):
        loc = f"A-{i}"
        if loc not in used:
            return loc

    return "A-0"

# ===== 全自動 OCR → 入庫 =====

@app.route("/api/auto_ocr", methods=["POST"])
def auto_ocr():

    file = request.files["file"]

    img = read_img(file)
    img = preprocess(img)

    text = ocr(img)
    text = apply_fix(text)

    parsed = parse_lines(text)

    c=conn(); cur=c.cursor()

    results = []

    for item in parsed:
        p = item["product"]
        q = item["qty"]

        loc = auto_location()

        cur.execute("SELECT qty FROM inventory WHERE product=%s",(p,))
        r = cur.fetchone()

        if r:
            cur.execute("UPDATE inventory SET qty=qty+%s WHERE product=%s",(q,p))
        else:
            cur.execute("INSERT INTO inventory VALUES(%s,%s,%s,'')",(p,q,loc))

        cur.execute("INSERT INTO logs(action) VALUES(%s)",(f"自動入庫 {p}",))

        results.append({
            "product":p,
            "qty":q,
            "location":loc
        })

    c.commit(); c.close()

    return jsonify({
        "text": text,
        "parsed": parsed,
        "result": results
    })

# ===== 查倉庫 =====
@app.route("/api/w")
def w():
    c=conn(); cur=c.cursor()
    cur.execute("SELECT product,qty,location FROM inventory")
    d=cur.fetchall(); c.close()
    return jsonify(d)

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