from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

from app.models import VpnConfig, VpnServer
from app.settings import settings
from app.services import wg_easy
from app.config import get_runtime_config


async def cleanup_expired_clients(db: Session, server: VpnServer | None = None) -> dict:
    servers = [server] if server else db.query(VpnServer).filter(VpnServer.is_active == True).all()  # noqa: E712
    now = datetime.now(timezone.utc)
    grace_days = max(int(get_runtime_config().get("app", {}).get("expired_config_grace_days", settings.expired_config_grace_days)), 0)
    cutoff = now - timedelta(days=grace_days)
    summary = {"servers": 0, "checked": 0, "deleted": 0, "errors": []}

    for row in servers:
        if row.protocol != "wg_easy":
            continue
        summary["servers"] += 1
        try:
            clients = await wg_easy.list_clients(row.code)
        except Exception as exc:
            summary["errors"].append(f"{row.code}: {exc}")
            continue

        for client in clients:
            summary["checked"] += 1
            client_id = client.get("id")
            name = client.get("name")
            expires_at = wg_easy.parse_wg_datetime(client.get("expiresAt"))
            if not client_id or not expires_at or expires_at > cutoff:
                continue
            try:
                await wg_easy.delete_client(row.code, client_id)
                summary["deleted"] += 1
                config = db.query(VpnConfig).filter(
                    VpnConfig.server_id == row.code,
                    VpnConfig.unique_code == name,
                ).order_by(VpnConfig.id.desc()).first()
                if config:
                    config.is_active = False
                    config.updated_at = datetime.utcnow()
            except Exception as exc:
                summary["errors"].append(f"{row.code}/{name or client_id}: {exc}")

    db.commit()
    return summary
