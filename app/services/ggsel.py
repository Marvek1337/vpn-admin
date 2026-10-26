import hashlib
import time
import httpx
from ..config import get_runtime_config


def _headers(token: str) -> dict:
    return {"Accept": "application/json", "Authorization": f"Bearer {token}"}


async def generate_token() -> str:
    cfg = get_runtime_config()["ggsel"]
    if not cfg.get("seller_id") or not cfg.get("api_key"):
        raise RuntimeError("GGSEL credentials are not configured")
    timestamp = str(int(time.time() * 1000))
    sign = hashlib.sha256(f"{cfg['api_key']}{timestamp}".encode("utf-8")).hexdigest()
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{cfg['base_url']}/apilogin",
            json={"seller_id": cfg["seller_id"], "timestamp": timestamp, "sign": sign},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        token = response.json().get("token")
    if not token:
        raise RuntimeError("Не удалось получить токен GGSEL")
    return token


async def check_purchase(unique_code: str, token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{get_runtime_config()['ggsel']['base_url']}/purchases/unique-code/{unique_code}",
            headers=_headers(token),
        )
        response.raise_for_status()
        return response.json()


async def get_product_data(product_id: int, token: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(
            f"{get_runtime_config()['ggsel']['base_url']}/products/{product_id}/data",
            headers=_headers(token),
        )
        response.raise_for_status()
        return response.json().get("product") or {}


def detect_period_key(purchase: dict) -> str:
    options = purchase.get("options") or []
    for option in options:
        name = str(option.get("name") or option.get("label") or "").strip().lower()
        value = str(option.get("value") or option.get("text") or "").strip().lower()
        if "период" not in name:
            continue
        if value in ("1 месяц", "1 month", "1 месяц/1 month"):
            return "30"
        if value in ("3 месяца", "3 month", "3 месяца/3 month"):
            return "90"
        if value in ("6 месяцев", "6 month", "6 месяцев/6 month"):
            return "180"
        if value in ("12 месяцев", "12 month", "12 месяцев/12 month"):
            return "360"
        if value in ("навсегда", "forever", "навсегда/forever"):
            return "forever"
        raise RuntimeError(f"Неизвестное значение периода: {value}")
    raise RuntimeError(f"Опция 'Период' не найдена: {options}")


async def set_product_active(product_id: int, enabled: bool, token: str | None = None) -> dict:
    cfg = get_runtime_config().get("ggsel", {})
    endpoint = cfg.get("product_update_endpoint")
    if not endpoint:
        return {"ok": False, "skipped": True, "reason": "product_update_endpoint is not configured"}
    own_token = False
    if not token:
        token = await generate_token()
        own_token = True
    payload_template = cfg.get("product_update_payload") or {
        "product_id": "{product_id}",
        "active": "{active}",
    }
    payload = {}
    for key, value in payload_template.items():
        if isinstance(value, str):
            payload[key] = value.format(product_id=product_id, active=str(enabled).lower())
        else:
            payload[key] = value
    url = endpoint.format(base_url=cfg.get("base_url", ""), product_id=product_id)
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload, headers=_headers(token))
        response.raise_for_status()
        try:
            data = response.json()
        except Exception:
            data = {"text": response.text}
    data["_used_generated_token"] = own_token
    return data
