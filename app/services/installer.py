from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy.orm import Session

from app.config import clear_runtime_config_cache
from app.models import (
    AdminAuditLog,
    AppSetting,
    ClaimRecord,
    Order,
    PaymentLog,
    ProductRoute,
    ServerStat,
    SubscriptionPeriod,
    TelegramAuthCode,
    User,
    VpnConfig,
    VpnServer,
)
from app.services.auth import hash_password


def is_installed(db: Session) -> bool:
    row = db.query(AppSetting).filter(AppSetting.key == "installed").first()
    return bool(row and str(row.value).lower() == "true")


def set_setting(db: Session, key: str, value: str | int | float | bool | None):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    value_text = "" if value is None else str(value)
    if row:
        row.value = value_text
        row.updated_at = datetime.utcnow()
    else:
        db.add(AppSetting(key=key, value=value_text))


def reset_database_for_install(db: Session):
    for model in (
        AdminAuditLog,
        PaymentLog,
        ClaimRecord,
        Order,
        VpnConfig,
        ServerStat,
        VpnServer,
        ProductRoute,
        SubscriptionPeriod,
        TelegramAuthCode,
        AppSetting,
        User,
    ):
        db.query(model).delete()
    db.flush()


def complete_install(db: Session, payload: dict):
    reset_database_for_install(db)

    admin = User(
        username=payload["admin_username"],
        password_hash=hash_password(payload["admin_password"]),
        is_admin=True,
    )
    db.add(admin)

    for key, value in payload["settings"].items():
        set_setting(db, key, value)
    set_setting(db, "installed", "true")
    set_setting(db, "installed_at", datetime.utcnow().isoformat())

    for index, item in enumerate(payload["periods"], start=1):
        db.add(SubscriptionPeriod(
            code=item["code"],
            label=item["label"],
            days=item["days"],
            price=item["price"],
            sort_order=index * 10,
            is_active=True,
        ))

    for item in payload["servers"]:
        db.add(VpnServer(
            code=item["code"],
            name=item["name"],
            country=item.get("country") or None,
            protocol="wg_easy",
            panel_url=item["api_url"],
            api_url=item["api_url"],
            server_host=item.get("server_host") or None,
            username=item.get("username") or None,
            password=item.get("password") or None,
            subnet=item.get("subnet") or None,
            min_free_ips=item.get("min_free_ips", 3),
            priority=item.get("priority", 100),
            is_active=True,
        ))

    for item in payload["products"]:
        db.add(ProductRoute(
            item_id=item["item_id"],
            name=item["name"],
            server_ids=json.dumps(item["server_ids"], ensure_ascii=False),
            is_active=True,
        ))

    db.commit()
    clear_runtime_config_cache()
