from __future__ import annotations

from flask import Blueprint, jsonify, request

from extensions import db
from models import InventoryItem, MasterOrderItem, Order, OrderItem, Shipment
from utils import (
    broadcast_refresh,
    create_activity_log,
    current_user,
    get_or_create_customer,
    login_required_json,
    parse_int,
)

order_api = Blueprint("order_api", __name__, url_prefix="/api/orders")


@order_api.get("")
@login_required_json
def list_orders():
    status = (request.args.get("status") or "").strip()
    query = Order.query.order_by(Order.created_at.desc())
    if status:
        query = query.filter_by(status=status)
    return jsonify({"ok": True, "orders": [order.to_dict() for order in query.all()]})


@order_api.put("/items/<int:item_id>")
@login_required_json
def update_order_item(item_id: int):
    user = current_user()
    item = OrderItem.query.get_or_404(item_id)
    data = request.get_json(silent=True) or {}
    new_qty = max(parse_int(data.get("quantity"), item.quantity), 0)

    if new_qty <= 0:
        return jsonify({"ok": False, "error": "數量必須大於 0"}), 400

    diff = new_qty - item.quantity
    if diff > 0 and item.inventory_item_id:
        source = InventoryItem.query.get(item.inventory_item_id)
        if not source or source.quantity < diff:
            return jsonify({"ok": False, "error": "庫存不足，已防止超賣"}), 400
        source.quantity -= diff
    elif diff < 0 and item.inventory_item_id:
        source = InventoryItem.query.get(item.inventory_item_id)
        if source:
            source.quantity += abs(diff)

    item.quantity = new_qty
    item.note = (data.get("note") or item.note).strip()
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="修改訂單",
        target_type="order",
        customer_name=item.order.customer.name if item.order and item.order.customer else "",
        product_name=item.product_name,
        quantity_delta=item.quantity,
        slot_label=item.slot_label,
        detail=f"修改訂單項目：{item.product_name} x {item.quantity}",
    )
    broadcast_refresh("order_item_updated")
    return jsonify({"ok": True, "item": item.to_dict()})


@order_api.delete("/items/<int:item_id>")
@login_required_json
def delete_order_item(item_id: int):
    user = current_user()
    item = OrderItem.query.get_or_404(item_id)
    if item.inventory_item_id and item.status != "shipped":
        source = InventoryItem.query.get(item.inventory_item_id)
        if source:
            source.quantity += item.quantity

    order_id = item.order_id
    detail = f"取消訂單項目：{item.product_name} x {item.quantity}"
    create_activity_log(
        actor=user.username,
        action_type="取消訂單",
        target_type="order",
        customer_name=item.order.customer.name if item.order and item.order.customer else "",
        product_name=item.product_name,
        quantity_delta=-item.quantity,
        slot_label=item.slot_label,
        detail=detail,
    )
    db.session.delete(item)
    db.session.commit()

    order = Order.query.get(order_id)
    if order and not order.items:
        db.session.delete(order)
        db.session.commit()

    broadcast_refresh("order_item_deleted")
    return jsonify({"ok": True})


@order_api.post("/items/<int:item_id>/ship")
@login_required_json
def ship_order_item(item_id: int):
    user = current_user()
    item = OrderItem.query.get_or_404(item_id)
    if item.status == "shipped":
        return jsonify({"ok": False, "error": "此項目已出貨"}), 400

    shipment = Shipment(
        customer_id=item.order.customer_id if item.order else None,
        product_name=item.product_name,
        spec=item.spec,
        quantity=item.quantity,
        unit=item.unit,
        order_item_id=item.id,
    )
    item.status = "shipped"
    if item.order:
        item.order.status = "partial" if any(i.status != "shipped" for i in item.order.items) else "shipped"

    db.session.add(shipment)
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="出貨",
        target_type="shipment",
        customer_name=item.order.customer.name if item.order and item.order.customer else "",
        product_name=item.product_name,
        quantity_delta=item.quantity,
        slot_label=item.slot_label,
        detail=f"出貨：{item.product_name} x {item.quantity}",
    )
    broadcast_refresh("shipment_created")
    return jsonify({"ok": True, "shipment": shipment.to_dict(), "item": item.to_dict()})


@order_api.post("/items/<int:item_id>/to-master")
@login_required_json
def order_item_to_master(item_id: int):
    user = current_user()
    item = OrderItem.query.get_or_404(item_id)
    master_item = MasterOrderItem(
        product_name=item.product_name,
        spec=item.spec,
        quantity=item.quantity,
        unit=item.unit,
        note=item.note,
        source_order_item_id=item.id,
    )
    db.session.add(master_item)
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="加入總單",
        target_type="master_order",
        customer_name="",
        product_name=item.product_name,
        quantity_delta=item.quantity,
        slot_label=item.slot_label,
        detail=f"加入總單：{item.product_name} x {item.quantity}",
    )
    broadcast_refresh("master_item_created")
    return jsonify({"ok": True, "master_item": master_item.to_dict()})


@order_api.post("/manual")
@login_required_json
def manual_order():
    user = current_user()
    data = request.get_json(silent=True) or {}
    customer = get_or_create_customer(data.get("customer_name"))
    if not customer:
        return jsonify({"ok": False, "error": "請輸入客戶名稱"}), 400

    qty = max(parse_int(data.get("quantity"), 0), 0)
    if qty <= 0:
        return jsonify({"ok": False, "error": "數量必須大於 0"}), 400

    order = Order(customer_id=customer.id, status="open")
    db.session.add(order)
    db.session.flush()

    item = OrderItem(
        order_id=order.id,
        product_name=(data.get("product_name") or "").strip() or "未命名商品",
        spec=(data.get("spec") or "").strip(),
        quantity=qty,
        unit=(data.get("unit") or "件").strip() or "件",
        note=(data.get("note") or "").strip(),
        slot_label=(data.get("slot_label") or "").strip(),
    )
    db.session.add(item)
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="新增訂單",
        target_type="order",
        customer_name=customer.name,
        product_name=item.product_name,
        quantity_delta=item.quantity,
        slot_label=item.slot_label,
        detail=f"手動建立訂單：{item.product_name} x {item.quantity}",
    )
    broadcast_refresh("order_manual_created")
    return jsonify({"ok": True, "order": order.to_dict()})
