from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import VpnServer, ServerStat, AdminAuditLog
from app.config import get_runtime_config


def server_to_runtime_dict(server: VpnServer) -> dict:
    return {
        "id": server.code,
        "code": server.code,
        "name": server.name,
        "country": server.country,
        "protocol": server.protocol,
        "url": server.api_url or server.panel_url or server.server_host,
        "panel_url": server.panel_url,
        "api_url": server.api_url,
        "user": server.username,
        "password": server.password,
        "api_token": server.api_token,
        "host": server.server_host,
        "subnet": server.subnet,
        "priority": server.priority,
        "max_clients": server.max_clients,
        "min_free_ips": server.min_free_ips,
        "active": server.is_active,
    }


def get_servers_from_db(active_only: bool = False) -> list[dict]:
    db = SessionLocal()
    try:
        q = db.query(VpnServer)
        if active_only:
            q = q.filter(VpnServer.is_active == True)  # noqa: E712
        rows = q.order_by(VpnServer.priority.asc(), VpnServer.id.asc()).all()
        return [server_to_runtime_dict(item) for item in rows]
    finally:
        db.close()


def get_runtime_with_db_servers() -> dict:
    runtime = get_runtime_config().copy()
    db_servers = get_servers_from_db()
    runtime["servers"] = db_servers
    runtime["server_map"] = {s["id"]: s for s in db_servers}
    runtime["server_names"] = {s["id"]: s["name"] for s in db_servers if s.get("active", True)}
    return runtime


def get_latest_server_stats(limit: int = 1000) -> dict[str, ServerStat]:
    db = SessionLocal()
    try:
        result: dict[str, ServerStat] = {}
        rows = db.query(ServerStat).order_by(ServerStat.id.desc()).limit(limit).all()
        for row in rows:
            result.setdefault(row.server_code, row)
        return result
    finally:
        db.close()


def audit(db: Session, admin_id: int | None, action: str, entity_type: str | None = None, entity_id: str | None = None, ip_address: str | None = None, payload: str | None = None):
    db.add(AdminAuditLog(
        admin_id=admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        payload=payload,
        created_at=datetime.utcnow(),
    ))
    db.commit()
