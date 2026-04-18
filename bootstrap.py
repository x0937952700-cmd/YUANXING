from werkzeug.security import generate_password_hash

from extensions import db
from models import User, WarehouseSlot


def seed_default_admin(app) -> None:
    username = app.config["DEFAULT_ADMIN_USERNAME"]
    password = app.config["DEFAULT_ADMIN_PASSWORD"]
    user = User.query.filter_by(username=username).first()
    if user:
        return
    user = User(username=username, password_hash=generate_password_hash(password), is_admin=True)
    db.session.add(user)
    db.session.commit()


def seed_default_warehouse() -> None:
    existing = WarehouseSlot.query.count()
    if existing > 0:
        return

    slots = []
    for zone in ("A", "B"):
        for band in range(1, 7):
            for row in ("front", "back"):
                for col in range(1, 11):
                    label = f"{zone}-{band}-{row[0].upper()}{col}"
                    slots.append(
                        WarehouseSlot(
                            zone=zone,
                            band=band,
                            row=row,
                            col_index=col,
                            label=label,
                            is_custom=False,
                            is_active=True,
                        )
                    )
    db.session.bulk_save_objects(slots)
    db.session.commit()
