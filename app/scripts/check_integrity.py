"""Report missing references without changing database records."""
import json

from app.database import SessionLocal
from app.models import ClaimRecord, Order, User, VpnConfig, VpnServer


def check_integrity(db) -> dict:
    users = {row.id for row in db.query(User).all()}
    servers = {row.code for row in db.query(VpnServer).all()}
    configs = {row.id: row for row in db.query(VpnConfig).all()}
    orders = {row.id: row for row in db.query(Order).all()}
    issues = []
    for config in configs.values():
        if config.user_id is not None and config.user_id not in users:
            issues.append(f"config {config.id}: missing user {config.user_id}")
        if config.server_id not in servers:
            issues.append(f"config {config.id}: missing server {config.server_id}")
    for order in orders.values():
        if order.config_id is not None and order.config_id not in configs:
            issues.append(f"order {order.id}: missing config {order.config_id}")
        if order.user_id is not None and order.user_id not in users:
            issues.append(f"order {order.id}: missing user {order.user_id}")
    for claim in db.query(ClaimRecord).all():
        if claim.config_id is None or claim.config_id not in configs:
            issues.append(f"claim {claim.id}: missing config {claim.config_id}")
        if claim.order_id is not None and claim.order_id not in orders:
            issues.append(f"claim {claim.id}: missing order {claim.order_id}")
    return {"ok": not issues, "issues": issues, "configs": len(configs), "orders": len(orders)}


if __name__ == "__main__":
    with SessionLocal() as db:
        result = check_integrity(db)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
