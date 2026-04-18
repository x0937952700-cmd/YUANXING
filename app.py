from flask import Flask, request, jsonify
import os

# ===== Flask =====
app = Flask(__name__)

# ===== OCR 安全導入（關鍵修復）=====
try:
    from ocr import process_ocr_text
except:
    process_ocr_text = None


# ===== 首頁 =====
@app.route("/")
def home():
    return "沅興木業 OCR 系統已上線"


# ===== OCR API（安全版）=====
@app.route("/ocr", methods=["POST"])
def ocr_api():
    if process_ocr_text is None:
        return jsonify({"error": "OCR 未啟用"}), 500

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "沒有檔案"}), 400

    result = process_ocr_text(file)
    return jsonify({"result": result})


# ===== DB 初始化 =====
def init_db():
    try:
        from db import get_conn
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS activity(
            id SERIAL PRIMARY KEY,
            action TEXT,
            time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()
        conn.close()
    except:
        print("DB 初始化略過")


init_db()


# ===== 啟動（Render關鍵）=====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)