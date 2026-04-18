from __future__ import annotations

import re
import unicodedata
from functools import wraps
from typing import Any

from flask import jsonify, session

from extensions import db, socketio
from models import ActivityLog, Customer, User, UserActivityState


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.strip().lower()
    value = re.sub(r"\s+", "", value)
    return value


def get_or_create_customer(name: str | None) -> Customer | None:
    raw_name = (name or "").strip()
    if not raw_name:
        return None
    normalized = normalize_name(raw_name)
    customer = Customer.query.filter_by(normalized_name=normalized).first()
    if customer:
        if customer.name != raw_name:
            customer.name = raw_name
            db.session.commit()
        return customer
    customer = Customer(name=raw_name, normalized_name=normalized)
    db.session.add(customer)
    db.session.commit()
    return customer


def current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)


def login_required_json(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"ok": False, "error": "請先登入"}), 401
        return func(*args, **kwargs)

    return wrapper


def get_or_create_user_activity_state(user: User) -> UserActivityState:
    state = UserActivityState.query.filter_by(user_id=user.id).first()
    if state:
        return state
    state = UserActivityState(user_id=user.id, last_seen_activity_id=0)
    db.session.add(state)
    db.session.commit()
    return state


def unread_activity_count(user: User) -> int:
    state = get_or_create_user_activity_state(user)
    return ActivityLog.query.filter(ActivityLog.id > state.last_seen_activity_id).count()


def create_activity_log(
    actor: str,
    action_type: str,
    target_type: str,
    customer_name: str = "",
    product_name: str = "",
    quantity_delta: int = 0,
    slot_label: str = "",
    detail: str = "",
) -> ActivityLog:
    log = ActivityLog(
        actor=actor,
        action_type=action_type,
        target_type=target_type,
        customer_name=customer_name,
        product_name=product_name,
        quantity_delta=quantity_delta,
        slot_label=slot_label,
        detail=detail,
    )
    db.session.add(log)
    db.session.commit()
    socketio.emit("data_changed", {"type": "activity", "activity_id": log.id})
    return log


def broadcast_refresh(reason: str) -> None:
    socketio.emit("data_changed", {"type": "refresh", "reason": reason})


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
