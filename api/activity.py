
from flask import Blueprint, jsonify
from core.db import activity

activity_api = Blueprint("activity_api", __name__)

@activity_api.route("/api/activity/feed")
def feed():
    return {"items":activity,"summary":{"unread":len(activity)}}

@activity_api.route("/api/activity/delete", methods=["POST"])
def delete():
    activity.clear()
    return {"success":True}
