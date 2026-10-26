from __future__ import annotations

from urllib.parse import urlparse

from app.services.server_registry import get_runtime_with_db_servers


def _browser_ping_url(server: dict) -> str | None:
    raw_url = (server.get("host") or server.get("api_url") or server.get("panel_url") or server.get("url") or "").strip()
    if not raw_url:
        return None
    parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed.geturl().rstrip("/")


def measure_user_visible_pings() -> dict:
    runtime = get_runtime_with_db_servers()
    servers = [server for server in runtime.get("servers", []) if server.get("active", True)]
    results = []

    name_counts: dict[str, int] = {}
    for server in servers:
        key = server["name"].strip().casefold()
        name_counts[key] = name_counts.get(key, 0) + 1

    for server in servers:
        duplicate_name = name_counts.get(server["name"].strip().casefold(), 0) > 1
        ping_url = _browser_ping_url(server)
        results.append({
            "id": server["id"],
            "code": server["code"],
            "name": server["name"],
            "country": server.get("country") or "",
            "label": f"{server['name']} · {server['code']}" if duplicate_name else server["name"],
            "ping_url": ping_url,
            "ok": False,
            "latency_ms": None,
            "recommended": False,
            "error": "" if ping_url else "URL для пользовательского пинга не настроен",
        })

    return {
        "mode": "browser",
        "recommended_server_id": None,
        "items": results,
    }
