from __future__ import annotations

from collections import defaultdict

from models import InventoryItem, MasterOrderItem, OrderItem, Shipment


def build_reconciliation_report() -> dict:
    order_totals = defaultdict(int)
    master_totals = defaultdict(int)
    shipped_totals = defaultdict(int)
    inventory_totals = defaultdict(int)

    for item in OrderItem.query.all():
        order_totals[(item.product_name, item.spec)] += item.quantity

    for item in MasterOrderItem.query.all():
        master_totals[(item.product_name, item.spec)] += item.quantity

    for item in Shipment.query.all():
        shipped_totals[(item.product_name, item.spec)] += item.quantity

    for item in InventoryItem.query.all():
        inventory_totals[(item.product_name, item.spec)] += item.quantity

    keys = set(order_totals.keys()) | set(master_totals.keys()) | set(shipped_totals.keys()) | set(inventory_totals.keys())

    rows = []
    for product_name, spec in sorted(keys):
        rows.append(
            {
                "product_name": product_name,
                "spec": spec,
                "order_qty": order_totals[(product_name, spec)],
                "master_qty": master_totals[(product_name, spec)],
                "shipped_qty": shipped_totals[(product_name, spec)],
                "inventory_qty": inventory_totals[(product_name, spec)],
                "has_difference": len(
                    {
                        order_totals[(product_name, spec)],
                        master_totals[(product_name, spec)],
                        shipped_totals[(product_name, spec)],
                    }
                )
                > 1,
            }
        )
    return {"rows": rows}
