from app import socketio
from db import get_conn
from __future__ import annotations

import base64
import io
import os
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from PIL import Image

from extensions import db
from models import InventoryItem, Order, OrderItem, WarehouseSlot
from services.ocr_service import run_ocr
from utils import (
    broadcast_refresh,
    create_activity_log,
    current_user,
    get_or_create_customer,
    login_required_json,
    parse_int,
)

inventory_api = Blueprint("inventory_api", __name__, url_prefix="/api/inventory")


def _save_uploaded_image(file_storage) -> str:
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    ext = Path(file_storage.filename or "upload.png").suffix.lower() or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = upload_folder / filename
    file_storage.save(filepath)
    return f"/static/uploads/{filename}"


def _save_base64_image(data_url: str) -> tuple[str, io.BytesIO]:
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    upload_folder.mkdir(parents=True, exist_ok=True)
    header, encoded = data_url.split(",", 1)
    raw = base64.b64decode(encoded)
    ext = ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = upload_folder / filename
    filepath.write_bytes(raw)
    return f"/static/uploads/{filename}", io.BytesIO(raw)


@inventory_api.get("")
@login_required_json
def list_inventory():
    search = (request.args.get("search") or "").strip().lower()
    query = InventoryItem.query.order_by(InventoryItem.created_at.desc())
    if search:
        query = query.filter(
            (InventoryItem.product_name.ilike(f"%{search}%"))
            | (InventoryItem.spec.ilike(f"%{search}%"))
            | (InventoryItem.note.ilike(f"%{search}%"))
        )
    items = [item.to_dict() for item in query.all()]
    return jsonify({"ok": True, "items": items})


@inventory_api.post("/create")
@login_required_json
def create_inventory():
    user = current_user()
    data = request.get_json(silent=True) or {}
    customer = get_or_create_customer(data.get("customer_name"))
    item = InventoryItem(
        product_name=(data.get("product_name") or "").strip() or "未命名商品",
        spec=(data.get("spec") or "").strip(),
        quantity=max(parse_int(data.get("quantity"), 0), 0),
        unit=(data.get("unit") or "件").strip() or "件",
        note=(data.get("note") or "").strip(),
        source_text=(data.get("source_text") or "").strip(),
        image_path=(data.get("image_path") or "").strip(),
        ocr_confidence=float(data.get("ocr_confidence") or 0.0),
        customer_id=customer.id if customer else None,
    )
    db.session.add(item)
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="新增",
        target_type="inventory",
        customer_name=customer.name if customer else "",
        product_name=item.product_name,
        quantity_delta=item.quantity,
        slot_label="",
        detail=f"新增庫存：{item.product_name} {item.spec} x {item.quantity}",
    )
    broadcast_refresh("inventory_created")
    return jsonify({"ok": True, "item": item.to_dict()})


@inventory_api.put("/<int:item_id>")
@login_required_json
def update_inventory(item_id: int):
    user = current_user()
    item = InventoryItem.query.get_or_404(item_id)
    data = request.get_json(silent=True) or {}
    customer = get_or_create_customer(data.get("customer_name"))

    item.product_name = (data.get("product_name") or item.product_name).strip()
    item.spec = (data.get("spec") or item.spec).strip()
    item.quantity = max(parse_int(data.get("quantity"), item.quantity), 0)
    item.unit = (data.get("unit") or item.unit).strip() or "件"
    item.note = (data.get("note") or item.note).strip()
    item.source_text = (data.get("source_text") or item.source_text).strip()
    item.ocr_confidence = float(data.get("ocr_confidence") or item.ocr_confidence or 0.0)
    item.customer_id = customer.id if customer else None
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="修改",
        target_type="inventory",
        customer_name=customer.name if customer else "",
        product_name=item.product_name,
        quantity_delta=item.quantity,
        slot_label=item.slot.label if item.slot else "",
        detail=f"修改庫存：{item.product_name} {item.spec} x {item.quantity}",
    )
    broadcast_refresh("inventory_updated")
    return jsonify({"ok": True, "item": item.to_dict()})


@inventory_api.delete("/<int:item_id>")
@login_required_json
def delete_inventory(item_id: int):
    user = current_user()
    item = InventoryItem.query.get_or_404(item_id)
    detail = f"刪除庫存：{item.product_name} {item.spec} x {item.quantity}"
    create_activity_log(
        actor=user.username,
        action_type="刪除",
        target_type="inventory",
        customer_name=item.customer.name if item.customer else "",
        product_name=item.product_name,
        quantity_delta=-item.quantity,
        slot_label=item.slot.label if item.slot else "",
        detail=detail,
    )
    db.session.delete(item)
    db.session.commit()
    broadcast_refresh("inventory_deleted")
    return jsonify({"ok": True})


@inventory_api.post("/ocr")
@login_required_json
def inventory_ocr():
    api_key = current_app.config["OCR_SPACE_API_KEY"]

    image_path = ""
    file_stream = None

    if "image" in request.files:
        uploaded = request.files["image"]
        image_path = _save_uploaded_image(uploaded)
        uploaded.stream.seek(0)
        file_stream = io.BytesIO(uploaded.stream.read())
    else:
        data = request.get_json(silent=True) or {}
        cropped_image = data.get("cropped_image")
        if not cropped_image:
            return jsonify({"ok": False, "error": "請提供圖片"}), 400
        image_path, file_stream = _save_base64_image(cropped_image)

    result = run_ocr(file_stream, api_key=api_key)
    return jsonify({"ok": True, "image_path": image_path, **result})


@inventory_api.post("/<int:item_id>/assign-slot")
@login_required_json
def assign_slot(item_id: int):
    user = current_user()
    item = InventoryItem.query.get_or_404(item_id)
    data = request.get_json(silent=True) or {}
    slot_id = parse_int(data.get("slot_id"))
    slot = WarehouseSlot.query.get_or_404(slot_id)

    occupied = next((row for row in slot.inventory_items if row.id != item.id and row.quantity > 0), None)
    if occupied:
        return jsonify({"ok": False, "error": "此格位已有商品，請先移走再配置"}), 400

    item.slot_id = slot.id
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="移動",
        target_type="warehouse",
        customer_name=item.customer.name if item.customer else "",
        product_name=item.product_name,
        quantity_delta=item.quantity,
        slot_label=slot.label,
        detail=f"商品放入倉位 {slot.label}",
    )
    broadcast_refresh("slot_assigned")
    return jsonify({"ok": True, "item": item.to_dict(), "slot": slot.to_dict()})


@inventory_api.post("/<int:item_id>/unassign")
@login_required_json
def unassign_slot(item_id: int):
    user = current_user()
    item = InventoryItem.query.get_or_404(item_id)
    old_slot = item.slot.label if item.slot else ""
    item.slot_id = None
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="移除倉位",
        target_type="warehouse",
        customer_name=item.customer.name if item.customer else "",
        product_name=item.product_name,
        quantity_delta=item.quantity,
        slot_label=old_slot,
        detail=f"移除倉位：{old_slot}",
    )
    broadcast_refresh("slot_unassigned")
    return jsonify({"ok": True, "item": item.to_dict()})


@inventory_api.post("/<int:item_id>/add-to-order")
@login_required_json
def add_to_order(item_id: int):
    user = current_user()
    item = InventoryItem.query.get_or_404(item_id)
    data = request.get_json(silent=True) or {}
    customer = get_or_create_customer(data.get("customer_name"))
    if not customer:
        return jsonify({"ok": False, "error": "請輸入客戶名稱"}), 400

    qty = max(parse_int(data.get("quantity"), 0), 0)
    if qty <= 0:
        return jsonify({"ok": False, "error": "數量必須大於 0"}), 400

    if item.quantity < qty:
        return jsonify({"ok": False, "error": "庫存不足，已防止超賣"}), 400

    order = Order(customer_id=customer.id, status="open")
    db.session.add(order)
    db.session.flush()

    order_item = OrderItem(
        order_id=order.id,
        inventory_item_id=item.id,
        product_name=item.product_name,
        spec=item.spec,
        quantity=qty,
        unit=item.unit,
        status="reserved",
        note=(data.get("note") or "").strip(),
        slot_label=item.slot.label if item.slot else "",
    )
    item.quantity -= qty
    db.session.add(order_item)
    db.session.commit()

    create_activity_log(
        actor=user.username,
        action_type="加入訂單",
        target_type="order",
        customer_name=customer.name,
        product_name=item.product_name,
        quantity_delta=qty,
        slot_label=item.slot.label if item.slot else "",
        detail=f"從庫存加入訂單：{item.product_name} x {qty}",
    )
    broadcast_refresh("order_created")
    return jsonify({"ok": True, "order": order.to_dict(), "inventory_item": item.to_dict()})

# DB insert example

socketio.emit('update')
