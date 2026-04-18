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
        product TEXT PRIMARY KEY,
        qty INT,
        location TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS ocr_fix(
        wrong TEXT PRIMARY KEY,
        correct TEXT
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

# ===== OCR學習 =====
@app.route("/api/ocr_learn", methods=["POST"])
def learn():
    d=request.json
    conn=get_conn();c=conn.cursor()

    c.execute("""
    INSERT INTO ocr_fix(wrong,correct)
    VALUES(%s,%s)
    ON CONFLICT (wrong) DO UPDATE SET correct=%s
    """,(d["w"],d["c"],d["c"]))

    conn.commit()
    return jsonify({"ok":1})

# ===== OCR套用 =====
@app.route("/api/ocr_apply")
def apply():
    text=request.args.get("t","")

    conn=get_conn();c=conn.cursor()
    c.execute("SELECT wrong,correct FROM ocr_fix")
    rows=c.fetchall()

    for w,corr in rows:
        text=text.replace(w,corr)

    return jsonify({"text":text})

# ===== 入庫 =====
@app.route("/api/add", methods=["POST"])
def add():
    d=request.json
    conn=get_conn();c=conn.cursor()

    c.execute("SELECT qty FROM inventory WHERE product=%s",(d["p"],))
    r=c.fetchone()

    if r:
        c.execute("UPDATE inventory SET qty=qty+%s WHERE product=%s",(d["q"],d["p"]))
    else:
        c.execute("INSERT INTO inventory(product,qty,location) VALUES(%s,%s,%s)",
                  (d["p"],d["q"],""))

    conn.commit()
    return jsonify({"ok":1})

# ===== 拖拉更新位置 =====
@app.route("/api/move", methods=["POST"])
def move():
    d=request.json
    conn=get_conn();c=conn.cursor()

    c.execute("UPDATE inventory SET location=%s WHERE product=%s",
              (d["loc"],d["p"]))

    conn.commit()
    return jsonify({"ok":1})

# ===== 倉庫 =====
@app.route("/api/warehouse")
def warehouse():
    conn=get_conn();c=conn.cursor()
    c.execute("SELECT product,qty,location FROM inventory")
    rows=c.fetchall()
    return jsonify([{"p":r[0],"q":r[1],"l":r[2]} for r in rows])

if __name__=="__main__":
    app.run(host="0.0.0.0",port=10000)
