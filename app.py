
from flask import Flask, render_template
from flask_socketio import SocketIO
import os

from api.auth import auth_api
from api.inventory import inventory_api
from api.warehouse import warehouse_api
from api.activity import activity_api

app = Flask(__name__)
app.secret_key = "secret"

socketio = SocketIO(app, cors_allowed_origins="*")

app.register_blueprint(auth_api)
app.register_blueprint(inventory_api)
app.register_blueprint(warehouse_api)
app.register_blueprint(activity_api)

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT",10000))
    socketio.run(app, host="0.0.0.0", port=port)
