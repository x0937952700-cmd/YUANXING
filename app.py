from flask import Flask, request, jsonify, render_template
import psycopg2, os

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# =========================
# 🔥 強制只用 index.html
# =========================
@app.route("/")
def home():
    return render_template("index.html")

# =========================
# OCR 學習
# =========================
@app.route("/api/ocr_learn", methods=["POST"])
def learn():
    d = request.json
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ocr_fix(
        w TEXT PRIMARY KEY,
        c TEXT
    )
    """)

    cur.execute("""
    INSERT INTO ocr_fix(w,c) VALUES(%s,%s)
    ON CONFLICT (w) DO UPDATE SET c=%s
    """, (d["w"], d["c"], d["c"]))

    conn.commit()
    conn.close()
    return jsonify({"ok": 1})

# =========================
# OCR 套用
# =========================
@app.route("/api/ocr_apply")
def apply():
    t = request.args.get("t", "")
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT w,c FROM ocr_fix")
    for w, c in cur.fetchall():
        t = t.replace(w, c)

    conn.close()
    return jsonify({"t": t})

# =========================
# 庫存
# =========================
@app.route("/api/add", methods=["POST"])
def add():
    d = request.json
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS inv(
        p TEXT PRIMARY KEY,
        q INT,
        l TEXT
    )
    """)

    cur.execute("SELECT q FROM inv WHERE p=%s", (d["p"],))
    r = cur.fetchone()

    if r:
        cur.execute("UPDATE inv SET q=q+%s WHERE p=%s", (d["q"], d["p"]))
    else:
        cur.execute("INSERT INTO inv VALUES(%s,%s,'')", (d["p"], d["q"]))

    conn.commit()
    conn.close()
    return jsonify({"ok": 1})

# =========================
# 拖拉
# =========================
@app.route("/api/move", methods=["POST"])
def move():
    d = request.json
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("UPDATE inv SET l=%s WHERE p=%s", (d["l"], d["p"]))

    conn.commit()
    conn.close()
    return jsonify({"ok": 1})

# =========================
# 倉庫資料
# =========================
@app.route("/api/w")
def w():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT p,q,l FROM inv")
    data = cur.fetchall()

    conn.close()
    return jsonify(data)

# =========================
# 🚀 關閉快取（超重要）
# =========================
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response

# =========================
# 啟動
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)