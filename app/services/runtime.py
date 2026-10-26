from .server_registry import get_runtime_with_db_servers
from . import wg_easy


def get_server(server_id: str) -> dict:
    runtime = get_runtime_with_db_servers()
    server = runtime["server_map"].get(server_id)
    if not server:
        raise ValueError("Server not found")
    return server


def get_product_by_item(item_id: int) -> dict | None:
    runtime = get_runtime_with_db_servers()
    return runtime["product_map"].get(int(item_id))


def get_period(period_key: str) -> dict:
    runtime = get_runtime_with_db_servers()
    period = runtime["periods"].get(period_key)
    if not period:
        raise ValueError("Unknown period")
    return period


def get_product_server_ids(product: dict) -> list[str]:
    server_ids = product.get("server_ids") or []
    if not server_ids and product.get("server_id"):
        server_ids = [product["server_id"]]
    return [server_id for server_id in server_ids if server_id]


async def select_best_server_for_product(product: dict) -> tuple[str | None, list[dict]]:
    server_ids = get_product_server_ids(product)
    checks: list[dict] = []
    for server_id in server_ids:
        try:
            capacity = await wg_easy.get_server_capacity(server_id)
        except Exception as exc:
            capacity = {
                "server_id": server_id,
                "sellable": False,
                "free_count": 0,
                "min_free_ips": None,
                "reason": f"error: {exc}",
            }
        checks.append(capacity)
    sellable = [item for item in checks if item.get("sellable")]
    sellable.sort(key=lambda item: item.get("free_count") or 0, reverse=True)
    if sellable:
        return sellable[0]["server_id"], checks
    return None, checks


async def get_sellable_server_names() -> dict[str, str]:
    runtime = get_runtime_with_db_servers()
    result: dict[str, str] = {}
    for server in runtime.get("servers", []):
        server_id = server["id"]
        if not server.get("active", True):
            continue
        try:
            capacity = await wg_easy.get_server_capacity(server_id)
        except Exception:
            continue
        if capacity.get("sellable"):
            result[server_id] = server["name"]
    return result
