
from flask import Blueprint, request, jsonify
from core.db import inventory

inventory_api = Blueprint("inventory_api", __name__)

@inventory_api.route("/api/upload_ocr", methods=["POST"])
def ocr():
    return {
        "text":"木板 30x20 5片",
        "confidence":92,
        "items":[{"name":"木板","qty":5}]
    }

@inventory_api.route("/api/inventory")
def get():
    return {"items":inventory}

@inventory_api.route("/api/inventory/add", methods=["POST"])
def add():
    d = request.json
    inventory.append(d)
    return {"success":True}
