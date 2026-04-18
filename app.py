from flask import Flask
from flask_socketio import SocketIO
import os

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*')

# ====== 首頁 ======
@app.route("/")
def home():
    return "沅興木業 OCR 系統已上線"

# ====== 初始化 DB ======
def init_extra():
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

init_extra()

# ====== 啟動（關鍵修復）======
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)