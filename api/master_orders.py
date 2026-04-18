from flask import Blueprint, jsonify, request

from extensions import db
from models import MasterOrderItem
from utils import broadcast_refresh, create_activity_log, current_user, login_required_json, parse_int

master_order_api = Blueprint("master_order_api", __name__, url_prefix="/api/master-orders")


@master_order_api.get("")
@login_required_json
def list_master_orders():
    items = MasterOrderItem.query.order_by(MasterOrderItem.created_at.desc()).all()
    return jsonify({"ok": True, "items": [item.to_dict() for item in items]})


@master_order_api.post("")
@login_required_json
def create_master_order():
    user = current_user()
    data = request.get_json(silent=True) or {}
    item = MasterOrderItem(
        product_name=(data.get("product_name") or "").strip() or "未命名商品",
        spec=(data.get("spec") or "").strip(),
        quantity=max(parse_int(data.get("quantity"), 0), 0),
        unit=(data.get("unit") or "件").strip() or "件",
        note=(data.get("note") or "").strip(),
    )
    db.session.add(item)
    db.session.commit()
    create_activity_log(
        actor=user.username,
        action_type="新增總單",
        target_type="master_order",
        product_name=item.product_name,
        quantity_delta=item.quantity,
        detail=f"新增總單：{item.product_name} x {item.quantity}",
    )
    broadcast_refresh("master_order_created")
    return jsonify({"ok": True, "item": item.to_dict()})


@master_order_api.delete("/<int:item_id>")
@login_required_json
def delete_master_order(item_id: int):
    user = current_user()
    item = MasterOrderItem.query.get_or_404(item_id)
    create_activity_log(
        actor=user.username,
        action_type="刪除總單",
        target_type="master_order",
        product_name=item.product_name,
        quantity_delta=-item.quantity,
        detail=f"刪除總單：{item.product_name} x {item.quantity}",
    )
    db.session.delete(item)
    db.session.commit()
    broadcast_refresh("master_order_deleted")
    return jsonify({"ok": True})
