
from flask import Flask
from flask_socketio import SocketIO
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*')

@app.route("/")
def home():
    return "沅興木業 OCR 系統已上線"

if __name__ == "__main__":
    socketio.run()

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
