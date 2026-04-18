from datetime import datetime

from flask import Blueprint, jsonify

from models import ActivityLog, InventoryItem, Shipment
from services.reconcile_service import build_reconciliation_report
from utils import (
    current_user,
    get_or_create_user_activity_state,
    login_required_json,
    unread_activity_count,
)
from extensions import db

activity_api = Blueprint("activity_api", __name__, url_prefix="/api/activity")


@activity_api.get("/summary")
@login_required_json
def summary():
    user = current_user()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    added_today = ActivityLog.query.filter(
        ActivityLog.action_type == "新增",
        ActivityLog.created_at >= today_start,
    ).count()
    shipped_today = Shipment.query.filter(Shipment.created_at >= today_start).count()
    unassigned_count = InventoryItem.query.filter_by(slot_id=None).count()
    unread_count = unread_activity_count(user)
    return jsonify(
        {
            "ok": True,
            "summary": {
                "added_count": added_today,
                "shipped_count": shipped_today,
                "unassigned_count": unassigned_count,
                "unread_count": unread_count,
            },
        }
    )


@activity_api.get("/logs")
@login_required_json
def logs():
    rows = ActivityLog.query.order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(200).all()
    return jsonify({"ok": True, "logs": [row.to_dict() for row in rows]})


@activity_api.post("/mark-read")
@login_required_json
def mark_read():
    user = current_user()
    state = get_or_create_user_activity_state(user)
    max_id = db.session.query(db.func.max(ActivityLog.id)).scalar() or 0
    state.last_seen_activity_id = max_id
    db.session.commit()
    return jsonify({"ok": True, "unread_count": 0})


@activity_api.delete("/logs/<int:log_id>")
@login_required_json
def delete_log(log_id: int):
    log = ActivityLog.query.get_or_404(log_id)
    db.session.delete(log)
    db.session.commit()
    return jsonify({"ok": True})


@activity_api.get("/reconcile")
@login_required_json
def reconcile():
    return jsonify({"ok": True, "report": build_reconciliation_report()})
