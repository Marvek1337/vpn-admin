import json
from functools import lru_cache
from sqlalchemy.exc import SQLAlchemyError

from .database import SessionLocal
from .models import AppSetting, ProductRoute, SubscriptionPeriod
from .settings import settings

DEFAULT_PRIVACY_TEXT = """Политика конфиденциальности описывает, какие данные обрабатывает сервис при регистрации, оплате и выдаче цифрового доступа.

Сервис хранит минимальный набор данных: логин пользователя, историю заказов, статусы платежей, выданные конфигурации и технические журналы, необходимые для поддержки и безопасности.

Платежные данные обрабатываются платежным провайдером. Сервис не хранит данные банковских карт.

Данные используются для работы личного кабинета, выдачи и продления доступа, обработки обращений в поддержку и предотвращения злоупотреблений.

Владелец сервиса принимает разумные организационные и технические меры защиты данных. Пользователь может обратиться в поддержку по вопросам обработки данных."""

DEFAULT_TERMS_TEXT = """Пользовательское соглашение регулирует использование сервиса цифрового доступа.

Пользователь обязуется использовать сервис законно, не нарушать права третьих лиц и не совершать действий, которые могут повредить инфраструктуре сервиса.

Оплаченный доступ предоставляется в виде персональной конфигурации подключения. Срок действия, стоимость и доступная локация указываются перед оплатой.

После выдачи цифрового доступа возврат средств возможен только если услуга не была оказана по вине сервиса.

Владелец сервиса может ограничить доступ при нарушении условий, злоупотреблениях, попытках перепродажи доступа или требованиях законодательства.

Сервис предоставляется по принципу разумной доступности. Возможны технические работы, обновления и временные сбои инфраструктуры."""


def clear_runtime_config_cache() -> None:
    get_runtime_config.cache_clear()


def _decode_server_ids(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        raw = json.loads(value)
    except Exception:
        raw = []
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        server_id = str(item).strip()
        if server_id and server_id not in result:
            result.append(server_id)
    return result


def _setting_bool(setting_map: dict, key: str, default: bool = False) -> bool:
    if key not in setting_map or setting_map.get(key) is None:
        return default
    return str(setting_map.get(key)).strip().lower() in {"1", "true", "yes", "on", "да"}


def _setting_int(setting_map: dict, key: str, default: int) -> int:
    try:
        return int(str(setting_map.get(key, default)).strip())
    except (TypeError, ValueError):
        return default


def _runtime_from_db() -> dict:
    db = SessionLocal()
    try:
        setting_rows = db.query(AppSetting).all()
        setting_map = {row.key: row.value for row in setting_rows}
        app = {
            "brand": setting_map.get("brand") or "vpn-admin",
            "support_url": setting_map.get("support_url") or "",
            "public_base_url": setting_map.get("public_base_url") or settings.public_base_url,
            "expired_config_grace_days": _setting_int(setting_map, "expired_config_grace_days", settings.expired_config_grace_days),
            "privacy_text": setting_map.get("privacy_text") or DEFAULT_PRIVACY_TEXT,
            "terms_text": setting_map.get("terms_text") or DEFAULT_TERMS_TEXT,
        }

        periods = {}
        period_rows = db.query(SubscriptionPeriod).filter(
            SubscriptionPeriod.is_active == True  # noqa: E712
        ).order_by(SubscriptionPeriod.sort_order.asc(), SubscriptionPeriod.id.asc()).all()
        for row in period_rows:
            periods[row.code] = {
                "label": row.label,
                "days": row.days,
                "price": row.price,
            }

        products = []
        product_rows = db.query(ProductRoute).filter(
            ProductRoute.is_active == True  # noqa: E712
        ).order_by(ProductRoute.id.asc()).all()
        for row in product_rows:
            products.append({
                "item_id": row.item_id,
                "name": row.name,
                "server_ids": _decode_server_ids(row.server_ids),
            })
    finally:
        db.close()

    return {
        "app": app,
        "periods": periods,
        "products": products,
        "_settings": setting_map,
    }


@lru_cache(maxsize=1)
def get_runtime_config() -> dict:
    try:
        raw = _runtime_from_db()
    except SQLAlchemyError:
        raw = {"app": {}, "periods": {}, "products": {}, "_settings": {}}

    periods = raw.get("periods", {})
    products = raw.get("products", [])

    for product in products:
        if product.get("server_ids"):
            product["server_ids"] = [str(item) for item in product["server_ids"] if item]
        elif product.get("server_id"):
            product["server_ids"] = [str(product["server_id"])]
        else:
            product["server_ids"] = []

    raw["ggsel"] = {
        "base_url": raw.get("_settings", {}).get("ggsel_base_url") or settings.ggsel_base_url,
        "seller_id": raw.get("_settings", {}).get("ggsel_seller_id") or settings.ggsel_seller_id,
        "api_key": raw.get("_settings", {}).get("ggsel_api_key") or settings.ggsel_api_key,
        "product_update_endpoint": raw.get("_settings", {}).get("ggsel_product_update_endpoint") or settings.ggsel_product_update_endpoint,
        "product_update_payload": settings.ggsel_product_update_payload,
    }
    raw["platega"] = {
        "enabled": _setting_bool(raw.get("_settings", {}), "platega_enabled", settings.platega_enabled),
        "base_url": raw.get("_settings", {}).get("platega_base_url") or settings.platega_base_url,
        "merchant_id": raw.get("_settings", {}).get("platega_merchant_id") or settings.platega_merchant_id,
        "secret": raw.get("_settings", {}).get("platega_secret") or settings.platega_secret,
        "payment_method": _setting_int(raw.get("_settings", {}), "platega_payment_method", settings.platega_payment_method),
        "currency": raw.get("_settings", {}).get("platega_currency") or settings.platega_currency,
        "callback_secret": raw.get("_settings", {}).get("platega_callback_secret") or settings.platega_callback_secret,
    }
    raw["telegram"] = {
        "bot_token": raw.get("_settings", {}).get("telegram_bot_token") or "",
        "bot_username": raw.get("_settings", {}).get("telegram_bot_username") or "",
    }
    raw.pop("_settings", None)
    raw["servers"] = []
    raw["server_map"] = {}
    raw["server_names"] = {}
    raw["product_map"] = {int(p["item_id"]): p for p in products}
    raw["period_labels"] = {k: v["label"] for k, v in periods.items()}
    raw["period_prices"] = {k: v["price"] for k, v in periods.items()}
    raw["period_days"] = {k: v.get("days") for k, v in periods.items()}
    return raw
