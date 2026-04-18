from pathlib import Path

from flask import Flask, jsonify, render_template, send_from_directory

from backup import list_backups, run_daily_backup
from bootstrap import seed_default_admin, seed_default_warehouse
from config import Config
from extensions import db, socketio
from api.auth import auth_api
from api.inventory import inventory_api
from api.orders import order_api
from api.master_orders import master_order_api
from api.warehouse import warehouse_api
from api.activity import activity_api
from utils import login_required_json


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    instance_dir = Path(app.root_path) / "instance"
    instance_dir.mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    socketio.init_app(app)

    app.register_blueprint(auth_api)
    app.register_blueprint(inventory_api)
    app.register_blueprint(order_api)
    app.register_blueprint(master_order_api)
    app.register_blueprint(warehouse_api)
    app.register_blueprint(activity_api)

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return "OK"

    @app.get("/manifest.json")
    def manifest():
        return send_from_directory("static", "manifest.json")

    @app.get("/manifest.webmanifest")
    def manifest_webmanifest():
        return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

    @app.get("/sw.js")
    def service_worker():
        return send_from_directory("static", "sw.js", mimetype="application/javascript")

    @app.get("/service-worker.js")
    def service_worker_alias():
        return send_from_directory("static", "service-worker.js", mimetype="application/javascript")

    @app.post("/api/backup")
    @login_required_json
    def backup_now():
        return jsonify(run_daily_backup())

    @app.get("/api/backups")
    @login_required_json
    def backup_list():
        return jsonify(list_backups())

    with app.app_context():
        db.create_all()
        seed_default_admin(app)
        seed_default_warehouse()

    return app


app = create_app()


if __name__ == "__main__":
    port = int(__import__("os").environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)
