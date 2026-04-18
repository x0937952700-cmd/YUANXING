from flask import Blueprint, jsonify, request, session

from models import User
from utils import current_user

auth_api = Blueprint("auth_api", __name__, url_prefix="/api/auth")


@auth_api.get("/me")
def me():
    user = current_user()
    return jsonify({"ok": True, "user": user.to_dict() if user else None})


@auth_api.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not user.verify_password(password):
        return jsonify({"ok": False, "error": "帳號或密碼錯誤"}), 400

    session["user_id"] = user.id
    return jsonify({"ok": True, "user": user.to_dict()})


@auth_api.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})
