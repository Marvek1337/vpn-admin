from datetime import datetime, timedelta, timezone
import asyncio
import ipaddress
import httpx
from ..services.runtime import get_server


def _auth(server: dict) -> tuple[str, str]:
    return server["user"], server["password"]


def parse_wg_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        if value.endswith("Z"):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


async def _request(method: str, server_id: str, path: str, **kwargs) -> httpx.Response:
    server = get_server(server_id)
    timeout = kwargs.pop("timeout", 15)
    async with httpx.AsyncClient(timeout=timeout, auth=_auth(server)) as client:
        response = await client.request(method, f"{server['url'].rstrip('/')}{path}", **kwargs)
        response.raise_for_status()
        return response


async def list_clients(server_id: str) -> list[dict]:
    response = await _request("GET", server_id, "/api/client", timeout=10)
    data = response.json()
    return data if isinstance(data, list) else []


async def find_client(server_id: str, name: str) -> dict | None:
    for client in await list_clients(server_id):
        if client.get("name") == name:
            return client
    return None


async def create_client(server_id: str, name: str, expires_at: datetime | None, retries: int = 3) -> dict:
    payload = {"name": name}
    if expires_at is not None:
        payload["expiresAt"] = expires_at.astimezone(timezone.utc).isoformat()

    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            response = await _request("POST", server_id, "/api/client", json=payload, timeout=15)
            try:
                data = response.json()
            except Exception:
                data = {}
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < retries:
                await asyncio.sleep(0.7 * (attempt + 1))
    raise RuntimeError(f"Не удалось создать WG-клиента на {server_id}: {last_exc}")


async def update_client(server_id: str, client: dict, expires_at=None, enabled: bool = True, name: str | None = None) -> dict:
    payload = dict(client)
    if name is not None:
        payload["name"] = name
    payload["enabled"] = enabled

    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        else:
            expires_at = expires_at.astimezone(timezone.utc)
        payload["expiresAt"] = expires_at.isoformat().replace("+00:00", "Z")
    else:
        payload["expiresAt"] = None

    response = await _request("POST", server_id, f"/api/client/{client['id']}", json=payload, timeout=15)
    return response.json()


async def get_client_config(server_id: str, client_id: str | int) -> str:
    response = await _request("GET", server_id, f"/api/client/{client_id}/configuration", timeout=10)
    return response.text


async def delete_client(server_id: str, client_id: str | int) -> bool:
    response = await _request("DELETE", server_id, f"/api/client/{client_id}", timeout=10)
    return response.status_code in {200, 204}


def compute_expires_at(period_days: int | None, current_expires_at: datetime | None = None) -> datetime | None:
    if period_days is None:
        return None
    now = datetime.now(timezone.utc)
    if current_expires_at is not None:
        if current_expires_at.tzinfo is None:
            current_expires_at = current_expires_at.replace(tzinfo=timezone.utc)
        else:
            current_expires_at = current_expires_at.astimezone(timezone.utc)
    base = current_expires_at if current_expires_at and current_expires_at > now else now
    return base + timedelta(days=period_days)


def calculate_free_ips(clients: list[dict], subnet: str) -> tuple[set[str], set[str], list[str]]:
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
    free_ips = sorted(all_ips - used_ips, key=ipaddress.ip_address)
    return all_ips, used_ips, free_ips


async def get_server_capacity(server_id: str) -> dict:
    server = get_server(server_id)
    subnet = server.get("subnet")
    min_free_ips = int(server.get("min_free_ips", 3) or 3)
    if not subnet:
        return {
            "server_id": server_id,
            "subnet": None,
            "clients_total": None,
            "used_count": None,
            "free_count": None,
            "min_free_ips": min_free_ips,
            "sellable": bool(server.get("active", True)),
            "reason": "subnet_not_configured",
        }
    clients = await list_clients(server_id)
    all_ips, used_ips, free_ips = calculate_free_ips(clients, subnet)
    return {
        "server_id": server_id,
        "subnet": subnet,
        "clients_total": len(clients),
        "used_count": len(used_ips),
        "free_count": len(free_ips),
        "min_free_ips": min_free_ips,
        "sellable": bool(server.get("active", True)) and len(free_ips) >= min_free_ips,
        "reason": "ok" if len(free_ips) >= min_free_ips else "low_free_ips",
    }
