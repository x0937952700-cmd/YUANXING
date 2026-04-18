
from flask import request, jsonify
from flask_socketio import SocketIO
import datetime

socketio = SocketIO(cors_allowed_origins="*")

inventory=[]
warehouse={}
activity=[]

def log(msg):
    activity.insert(0,{"action":msg,"time":str(datetime.datetime.now())})

def register_api(app):
    socketio.init_app(app)

    @app.route("/api/ocr/upload",methods=["POST"])
    def ocr():
        return {"text":"OCR測試","confidence":0.9}

    @app.route("/api/inventory/add_from_ocr",methods=["POST"])
    def add():
        data=request.json
        inventory.append(data.get("text",""))
        log("新增庫存")
        socketio.emit("update")
        return {"ok":True}

    @app.route("/api/warehouse/place",methods=["POST"])
    def place():
        data=request.json
        warehouse[data["slot"]]=data["item"]
        log("放入倉庫")
        socketio.emit("update")
        return {"ok":True}

    @app.route("/api/search")
    def search():
        q=request.args.get("q","")
        return {k:v for k,v in warehouse.items() if q in v}

    @app.route("/api/activity")
    def act():
        return activity[:20]
