from flask import Flask, request, jsonify, render_template
import psycopg2, os

app = Flask(__name__)
DB = os.environ.get("DATABASE_URL")

def conn():
    return psycopg2.connect(DB, sslmode='require')

@app.route("/")
def home():
    return render_template("index.html")

# OCR學習
@app.route("/api/ocr_learn", methods=["POST"])
def learn():
    d=request.json
    c=conn();cur=c.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ocr_fix(w TEXT PRIMARY KEY,c TEXT)
    """)
    cur.execute("""
    INSERT INTO ocr_fix(w,c) VALUES(%s,%s)
    ON CONFLICT (w) DO UPDATE SET c=%s
    """,(d["w"],d["c"],d["c"]))
    c.commit()
    return jsonify({"ok":1})

# OCR套用
@app.route("/api/ocr_apply")
def apply():
    t=request.args.get("t","")
    c=conn();cur=c.cursor()
    cur.execute("SELECT w,c FROM ocr_fix")
    for w,corr in cur.fetchall():
        t=t.replace(w,corr)
    return jsonify({"t":t})

# 庫存
@app.route("/api/add", methods=["POST"])
def add():
    d=request.json
    c=conn();cur=c.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS inv(p TEXT PRIMARY KEY,q INT,l TEXT)
    """)

    cur.execute("SELECT q FROM inv WHERE p=%s",(d["p"],))
    r=cur.fetchone()

    if r:
        cur.execute("UPDATE inv SET q=q+%s WHERE p=%s",(d["q"],d["p"]))
    else:
        cur.execute("INSERT INTO inv VALUES(%s,%s,'')",(d["p"],d["q"]))

    c.commit()
    return jsonify({"ok":1})

# 拖拉
@app.route("/api/move", methods=["POST"])
def move():
    d=request.json
    c=conn();cur=c.cursor()
    cur.execute("UPDATE inv SET l=%s WHERE p=%s",(d["l"],d["p"]))
    c.commit()
    return jsonify({"ok":1})

# 倉庫
@app.route("/api/w")
def w():
    c=conn();cur=c.cursor()
    cur.execute("SELECT p,q,l FROM inv")
    return jsonify(cur.fetchall())

app.run(host="0.0.0.0",port=10000)
