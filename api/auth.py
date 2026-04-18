
from flask import Blueprint, request, jsonify
from core.db import users

auth_api = Blueprint("auth_api", __name__)

@auth_api.route("/api/login", methods=["POST"])
def login():
    d = request.json
    if users.get(d["username"]) == d["password"]:
        return {"success":True,"user":{"name":d["username"]}}
    return {"success":False}
