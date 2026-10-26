import hmac
import httpx
from ..config import get_runtime_config
from ..settings import settings


PLATEGA_METHODS = {
    "sbp_qr": 2,
    "card": 11,
    "crypto": 13,
}


async def create_platega_link(order, method: str) -> dict:
    runtime = get_runtime_config()
    cfg = runtime["platega"]
    public_base_url = runtime.get("app", {}).get("public_base_url") or settings.public_base_url
    if not cfg.get("enabled"):
        if settings.app_env == "prod" or not settings.allow_test_payments:
            raise RuntimeError("Payments are not configured")
        return {
            "redirect": f"{public_base_url.rstrip('/')}/payments/mock/{order.id}",
            "transaction_id": f"mock-{order.id}",
            "status": "PENDING",
        }

    payment_method = PLATEGA_METHODS.get(method)
    if not payment_method:
        raise ValueError("Unsupported payment method")
    if not cfg.get("merchant_id") or not cfg.get("secret"):
        raise RuntimeError("Platega credentials are not configured")

    payload = {
        "paymentMethod": payment_method,
        "paymentDetails": {
            "amount": int(order.amount),
            "currency": cfg.get("currency", "RUB"),
        },
        "description": f"Заказ #{order.id} — {order.action}",
        "return": f"{public_base_url.rstrip('/')}/payments/result?order_id={order.id}",
        "failedUrl": f"{public_base_url.rstrip('/')}/payments/result?order_id={order.id}",
        "payload": str(order.id),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{cfg['base_url'].rstrip('/')}/transaction/process",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-MerchantId": cfg["merchant_id"],
                "X-Secret": cfg["secret"],
            },
        )
        response.raise_for_status()
        data = response.json()
    if not data.get("redirect") or not data.get("transactionId"):
        raise RuntimeError("Payment provider returned incomplete response")
    return {
        "redirect": data.get("redirect"),
        "transaction_id": data.get("transactionId"),
        "status": data.get("status"),
    }


def verify_callback(headers: dict) -> bool:
    runtime = get_runtime_config()
    cfg = runtime["platega"]
    if not cfg.get("enabled"):
        return False
    if not cfg.get("merchant_id") or not cfg.get("secret"):
        return False
    normalized = {str(k).lower(): v for k, v in headers.items()}
    return (
        hmac.compare_digest(str(normalized.get("x-merchantid", "")), str(cfg["merchant_id"]))
        and hmac.compare_digest(str(normalized.get("x-secret", "")), str(cfg["secret"]))
    )
