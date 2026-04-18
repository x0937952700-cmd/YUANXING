from __future__ import annotations

from datetime import datetime
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def verify_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "is_admin": self.is_admin,
        }


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), unique=True, nullable=False, index=True)
    normalized_name = db.Column(db.String(160), unique=True, nullable=False, index=True)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name}


class WarehouseSlot(TimestampMixin, db.Model):
    __tablename__ = "warehouse_slots"

    id = db.Column(db.Integer, primary_key=True)
    zone = db.Column(db.String(8), nullable=False)
    band = db.Column(db.Integer, nullable=False)
    row = db.Column(db.String(16), nullable=False)
    col_index = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(80), unique=True, nullable=False, index=True)
    is_custom = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    note = db.Column(db.Text, default="", nullable=False)

    inventory_items = db.relationship("InventoryItem", back_populates="slot", lazy=True)

    def to_dict(self) -> dict[str, Any]:
        item = next((x for x in self.inventory_items if x.quantity > 0), None)
        return {
            "id": self.id,
            "zone": self.zone,
            "band": self.band,
            "row": self.row,
            "col_index": self.col_index,
            "label": self.label,
            "is_custom": self.is_custom,
            "is_active": self.is_active,
            "note": self.note,
            "item": item.to_dict_min() if item else None,
        }


class InventoryItem(TimestampMixin, db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200), nullable=False, index=True)
    spec = db.Column(db.String(200), default="", nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    unit = db.Column(db.String(40), default="件", nullable=False)
    note = db.Column(db.Text, default="", nullable=False)
    source_text = db.Column(db.Text, default="", nullable=False)
    image_path = db.Column(db.String(255), default="", nullable=False)
    ocr_confidence = db.Column(db.Float, default=0.0, nullable=False)

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("warehouse_slots.id"), nullable=True)

    customer = db.relationship("Customer", lazy=True)
    slot = db.relationship("WarehouseSlot", back_populates="inventory_items", lazy=True)

    def to_dict_min(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "product_name": self.product_name,
            "spec": self.spec,
            "quantity": self.quantity,
            "unit": self.unit,
            "slot_label": self.slot.label if self.slot else None,
            "customer_name": self.customer.name if self.customer else "",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "product_name": self.product_name,
            "spec": self.spec,
            "quantity": self.quantity,
            "unit": self.unit,
            "note": self.note,
            "source_text": self.source_text,
            "image_path": self.image_path,
            "ocr_confidence": round(self.ocr_confidence or 0.0, 2),
            "customer_name": self.customer.name if self.customer else "",
            "slot_id": self.slot_id,
            "slot_label": self.slot.label if self.slot else None,
            "is_unassigned": self.slot_id is None,
            "created_at": self.created_at.isoformat(),
        }


class Order(TimestampMixin, db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    status = db.Column(db.String(40), default="open", nullable=False, index=True)

    customer = db.relationship("Customer", lazy=True)
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "customer_name": self.customer.name if self.customer else "",
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "created_at": self.created_at.isoformat(),
        }


class OrderItem(TimestampMixin, db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    inventory_item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=True)
    product_name = db.Column(db.String(200), nullable=False)
    spec = db.Column(db.String(200), default="", nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    unit = db.Column(db.String(40), default="件", nullable=False)
    status = db.Column(db.String(40), default="reserved", nullable=False, index=True)
    note = db.Column(db.Text, default="", nullable=False)
    slot_label = db.Column(db.String(80), default="", nullable=False)

    order = db.relationship("Order", back_populates="items", lazy=True)
    inventory_item = db.relationship("InventoryItem", lazy=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "customer_name": self.order.customer.name if self.order and self.order.customer else "",
            "product_name": self.product_name,
            "spec": self.spec,
            "quantity": self.quantity,
            "unit": self.unit,
            "status": self.status,
            "note": self.note,
            "slot_label": self.slot_label,
            "inventory_item_id": self.inventory_item_id,
            "created_at": self.created_at.isoformat(),
        }


class MasterOrderItem(TimestampMixin, db.Model):
    __tablename__ = "master_order_items"

    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(200), nullable=False, index=True)
    spec = db.Column(db.String(200), default="", nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    unit = db.Column(db.String(40), default="件", nullable=False)
    note = db.Column(db.Text, default="", nullable=False)
    source_order_item_id = db.Column(db.Integer, db.ForeignKey("order_items.id"), nullable=True)

    source_order_item = db.relationship("OrderItem", lazy=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "product_name": self.product_name,
            "spec": self.spec,
            "quantity": self.quantity,
            "unit": self.unit,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }


class Shipment(TimestampMixin, db.Model):
    __tablename__ = "shipments"

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    product_name = db.Column(db.String(200), nullable=False)
    spec = db.Column(db.String(200), default="", nullable=False)
    quantity = db.Column(db.Integer, default=0, nullable=False)
    unit = db.Column(db.String(40), default="件", nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_items.id"), nullable=True)

    customer = db.relationship("Customer", lazy=True)
    order_item = db.relationship("OrderItem", lazy=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "customer_name": self.customer.name if self.customer else "",
            "product_name": self.product_name,
            "spec": self.spec,
            "quantity": self.quantity,
            "unit": self.unit,
            "created_at": self.created_at.isoformat(),
        }


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(80), nullable=False, index=True)
    action_type = db.Column(db.String(80), nullable=False, index=True)
    target_type = db.Column(db.String(80), nullable=False)
    customer_name = db.Column(db.String(160), default="", nullable=False)
    product_name = db.Column(db.String(200), default="", nullable=False)
    quantity_delta = db.Column(db.Integer, default=0, nullable=False)
    slot_label = db.Column(db.String(80), default="", nullable=False)
    detail = db.Column(db.Text, default="", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "actor": self.actor,
            "action_type": self.action_type,
            "target_type": self.target_type,
            "customer_name": self.customer_name,
            "product_name": self.product_name,
            "quantity_delta": self.quantity_delta,
            "slot_label": self.slot_label,
            "detail": self.detail,
            "created_at": self.created_at.isoformat(),
        }


class UserActivityState(TimestampMixin, db.Model):
    __tablename__ = "user_activity_state"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    last_seen_activity_id = db.Column(db.Integer, default=0, nullable=False)

    user = db.relationship("User", lazy=True)
