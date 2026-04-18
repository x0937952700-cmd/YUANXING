from app import socketio
from db import get_conn
from flask import Blueprint, jsonify, request

from extensions import db
from models import InventoryItem, WarehouseSlot
from utils import broadcast_refresh, create_activity_log, current_user, login_required_json, parse_int

warehouse_api = Blueprint("warehouse_api", __name__, url_prefix="/api/warehouse")


@warehouse_api.get("/slots")
@login_required_json
def list_slots():
    slots = WarehouseSlot.query.filter_by(is_active=True).order_by(
        WarehouseSlot.zone.asc(),
        WarehouseSlot.band.asc(),
        WarehouseSlot.row.asc(),
        WarehouseSlot.col_index.asc(),
    )
    return jsonify({"ok": True, "slots": [slot.to_dict() for slot in slots]})


@warehouse_api.post("/slots")
@login_required_json
def create_slot():
    user = current_user()
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    if not label:
        zone = (data.get("zone") or "X").strip() or "X"
        band = max(parse_int(data.get("band"), 1), 1)
        row = (data.get("row") or "front").strip() or "front"
        col_index = max(parse_int(data.get("col_index"), 1), 1)
        label = f"{zone}-{band}-{row[0].upper()}{col_index}"

    slot = WarehouseSlot(
        zone=(data.get("zone") or "X").strip() or "X",
        band=max(parse_int(data.get("band"), 1), 1),
        row=(data.get("row") or "front").strip() or "front",
        col_index=max(parse_int(data.get("col_index"), 1), 1),
        label=label,
        is_custom=True,
        is_active=True,
        note=(data.get("note") or "").strip(),
    )
    db.session.add(slot)
    db.session.commit()
    create_activity_log(
        actor=user.username,
        action_type="新增格位",
        target_type="warehouse",
        slot_label=slot.label,
        detail=f"新增倉位：{slot.label}",
    )
    broadcast_refresh("slot_created")
    return jsonify({"ok": True, "slot": slot.to_dict()})


@warehouse_api.put("/slots/<int:slot_id>")
@login_required_json
def update_slot(slot_id: int):
    user = current_user()
    slot = WarehouseSlot.query.get_or_404(slot_id)
    data = request.get_json(silent=True) or {}
    slot.note = (data.get("note") or slot.note).strip()
    db.session.commit()
    create_activity_log(
        actor=user.username,
        action_type="修改格位",
        target_type="warehouse",
        slot_label=slot.label,
        detail=f"修改倉位：{slot.label}",
    )
    broadcast_refresh("slot_updated")
    return jsonify({"ok": True, "slot": slot.to_dict()})


@warehouse_api.delete("/slots/<int:slot_id>")
@login_required_json
def delete_slot(slot_id: int):
    user = current_user()
    slot = WarehouseSlot.query.get_or_404(slot_id)
    if slot.inventory_items:
        return jsonify({"ok": False, "error": "此格位仍有商品，無法刪除"}), 400
    if not slot.is_custom:
        return jsonify({"ok": False, "error": "預設格位不可刪除"}), 400

    create_activity_log(
        actor=user.username,
        action_type="刪除格位",
        target_type="warehouse",
        slot_label=slot.label,
        detail=f"刪除倉位：{slot.label}",
    )
    db.session.delete(slot)
    db.session.commit()
    broadcast_refresh("slot_deleted")
    return jsonify({"ok": True})


@warehouse_api.post("/move")
@login_required_json
def move_inventory():
    user = current_user()
    data = request.get_json(silent=True) or {}
    inventory_item_id = parse_int(data.get("inventory_item_id"))
    to_slot_id = parse_int(data.get("to_slot_id"))
    item = InventoryItem.query.get_or_404(inventory_item_id)
    slot = WarehouseSlot.query.get_or_404(to_slot_id)
    occupied = next((row for row in slot.inventory_items if row.id != item.id and row.quantity > 0), None)
    if occupied:
        return jsonify({"ok": False, "error": "此格位已有商品，請先移走再拖拉"}), 400
    item.slot_id = slot.id
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="拖拉移動",
        target_type="warehouse",
        customer_name=item.customer.name if item.customer else "",
        product_name=item.product_name,
        quantity_delta=item.quantity,
        slot_label=slot.label,
        detail=f"拖拉移動到 {slot.label}",
    )
    broadcast_refresh("inventory_moved")
    return jsonify({"ok": True, "item": item.to_dict(), "slot": slot.to_dict()})

# DB warehouse example

socketio.emit('update')
