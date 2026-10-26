from __future__ import annotations

import ipaddress
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.models import ServerStat, VpnServer


def server_to_monitoring_dict(server: VpnServer) -> dict:
    return {
        "db_id": server.id,
        "id": server.code,
        "name": server.name,
        "url": server.api_url or server.panel_url or server.server_host or "",
        "username": server.username or "",
        "password": server.password or "",
        "subnet": server.subnet or "",
        "country": server.country or "",
        "active": server.is_active,
        "min_free_ips": server.min_free_ips,
    }


async def get_clients(server: dict) -> list[dict]:
    url = f"{server['url'].rstrip('/')}/api/client"
    async with httpx.AsyncClient(timeout=10, auth=(server["username"], server["password"])) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    return data if isinstance(data, list) else []


def calculate_ip_stats(clients: list[dict], subnet: str) -> dict:
    network = ipaddress.ip_network(subnet)
    all_ips = {str(ip) for ip in network.hosts()}
    used_ips = set()

    for client in clients:
        address = client.get("address") or client.get("ipv4Address") or client.get("ipv4")
        if not address:
            continue
        ip = str(address).split("/")[0].strip()
        if ip in all_ips:
            used_ips.add(ip)

    free_ips = all_ips - used_ips
    return {
        "total": len(all_ips),
        "used": len(used_ips),
        "free": len(free_ips),
    }


async def collect_server_capacity(server: VpnServer) -> dict:
    item = server_to_monitoring_dict(server)
    item.update({
        "online": False,
        "clients_total": 0,
        "total": 0,
        "used": 0,
        "free": 0,
        "sellable": False,
        "error": None,
    })

    if not item["active"]:
        item["error"] = "Сервер отключен"
        return item
    if not item["url"]:
        item["error"] = "Не указан WG-Easy URL"
        return item
    if not item["username"] or not item["password"]:
        item["error"] = "Не указан логин или пароль WG-Easy"
        return item
    if not item["subnet"]:
        item["error"] = "Не указана подсеть"
        return item

    try:
        clients = await get_clients(item)
        stats = calculate_ip_stats(clients, item["subnet"])
        item.update({
            "online": True,
            "clients_total": len(clients),
            "total": stats["total"],
            "used": stats["used"],
            "free": stats["free"],
            "sellable": stats["free"] >= int(item["min_free_ips"] or 0),
        })
    except Exception as exc:
        item["error"] = str(exc)
    return item


def save_server_stat(db: Session, item: dict) -> None:
    db.add(ServerStat(
        server_code=item["id"],
        protocol="wg_easy",
        online=bool(item["online"]),
        total_clients=int(item["clients_total"] or 0),
        active_clients=int(item["clients_total"] or 0),
        free_ips=item["free"] if item["online"] else None,
        error=item.get("error"),
        created_at=datetime.utcnow(),
    ))


async def collect_all_servers_capacity(db: Session, persist: bool = False) -> dict:
    rows = db.query(VpnServer).filter(VpnServer.is_active == True).order_by(VpnServer.priority.asc(), VpnServer.id.asc()).all()  # noqa: E712
    items = []
    totals = {
        "total_servers": len(rows),
        "online_servers": 0,
        "total_ips": 0,
        "total_used": 0,
        "total_free": 0,
        "errors": 0,
    }

    for server in rows:
        item = await collect_server_capacity(server)
        items.append(item)
        if item["online"]:
            totals["online_servers"] += 1
            totals["total_ips"] += item["total"]
            totals["total_used"] += item["used"]
            totals["total_free"] += item["free"]
        else:
            totals["errors"] += 1
        if persist:
            save_server_stat(db, item)

    if persist:
        db.commit()
    return {"items": items, "totals": totals}
