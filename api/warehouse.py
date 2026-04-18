
from flask import Blueprint, request, jsonify
from core.db import warehouse

warehouse_api = Blueprint("warehouse_api", __name__)

@warehouse_api.route("/api/warehouse")
def get():
    return {"slots":warehouse}

@warehouse_api.route("/api/warehouse/cell", methods=["POST"])
def set_cell():
    d = request.json
    slot = d["slot"]   # A_1_front_1
    item = d["item"]

    if slot not in warehouse:
        warehouse[slot] = []

    warehouse[slot].append(item)
    return {"success":True}

@warehouse_api.route("/api/warehouse/search")
def search():
    q = request.args.get("q","")
    return {
        k:v for k,v in warehouse.items()
        if any(q in str(i) for i in v)
    }
