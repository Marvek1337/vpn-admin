from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from .server_registry import get_latest_server_stats, get_runtime_with_db_servers
from ..models import ClaimRecord, Order, VpnConfig
from ..core.statuses import OrderAction, OrderStatus, ProviderStatus
from ..crud import configs as crud_configs
from . import ggsel, wg_easy
from .runtime import get_product_by_item, get_server, select_best_server_for_product


PAID_STATES = {1, 3}
PAYMENT_METHOD_BY_PLATEGA_ID = {
    2: "sbp_qr",
    11: "card",
    13: "crypto",
}


def get_expires_at(created_at: datetime, period_days: int | None):
    if period_days is None:
        return None
    return created_at + timedelta(days=period_days)


async def build_runtime_context() -> dict:
    runtime = get_runtime_with_db_servers()
    latest_stats = get_latest_server_stats()
    sellable_server_names = {}
    sellable_server_options = []
    for server in runtime["servers"]:
        if not server.get("active", True):
            continue
        stat = latest_stats.get(server["id"])
        min_free_ips = int(server.get("min_free_ips", 3) or 3)
        free_count = stat.free_ips if stat else None

        # Рендер страниц не должен ждать WG-Easy. Если мониторинг уже запускался,
        # используем последнюю сохраненную емкость. Если данных пока нет, показываем
        # активный сервер, а финальную проверку делаем при создании заказа.
        if stat and (not stat.online or free_count is None or free_count < min_free_ips):
            continue

        option = {
            "id": server["id"],
            "code": server["code"],
            "name": server["name"],
            "country": server.get("country") or "",
            "priority": server.get("priority") or 100,
            "free_count": free_count,
            "min_free_ips": min_free_ips,
            "label": server["name"],
            "recommended": False,
            "duplicate_name": False,
        }
        sellable_server_options.append(option)

    name_counts: dict[str, int] = {}
    for option in sellable_server_options:
        key = option["name"].strip().casefold()
        name_counts[key] = name_counts.get(key, 0) + 1

    grouped_options: dict[str, dict] = {}
    ordered_group_keys: list[str] = []
    for option in sellable_server_options:
        key = option["name"].strip().casefold()
        duplicate_name = name_counts.get(key, 0) > 1
        option["duplicate_name"] = duplicate_name
        free = option.get("free_count")
        suffix = f" · свободно {free}" if free is not None else ""
        option["label"] = (
            f"{option['name']} · {option['code']}{suffix}"
            if duplicate_name
            else f"{option['name']}{suffix}"
        )
        if key not in grouped_options:
            grouped_options[key] = {"name": option["name"], "options": []}
            ordered_group_keys.append(key)
        grouped_options[key]["options"].append(option)

    sellable_server_groups = []
    for key in ordered_group_keys:
        group = grouped_options[key]
        group["options"].sort(key=lambda item: (-(item.get("free_count") or 0), item.get("priority") or 100, item["code"]))
        if group["options"]:
            group["options"][0]["recommended"] = len(group["options"]) > 1
            group["recommended_id"] = group["options"][0]["id"]
            group["recommended_code"] = group["options"][0]["code"]
        sellable_server_groups.append(group)

    sellable_server_options = [
        option
        for group in sellable_server_groups
        for option in group["options"]
    ]
    sellable_server_names = {option["id"]: option["label"] for option in sellable_server_options}
    return {
        "server_names": runtime["server_names"],
        "sellable_server_names": sellable_server_names,
        "sellable_server_options": sellable_server_options,
        "sellable_server_groups": sellable_server_groups,
        "period_labels": runtime["period_labels"],
        "period_prices": runtime["period_prices"],
        "period_days": runtime["period_days"],
        "brand": runtime.get("app", {}).get("brand", "vpn-admin"),
        "app": runtime.get("app", {}),
        "expired_config_grace_days": runtime.get("app", {}).get("expired_config_grace_days", 1),
        "payment_methods": {
            "sbp_qr": "СБП / QR",
            "card": "Банковская карта",
            "crypto": "Криптовалюта",
        },
        "default_payment_method": PAYMENT_METHOD_BY_PLATEGA_ID.get(int(runtime.get("platega", {}).get("payment_method") or 2), "sbp_qr"),
    }


async def _issue_purchase_config(db: Session, order: Order) -> VpnConfig:
    runtime = get_runtime_with_db_servers()
    period_days = runtime["period_days"][order.period_key]
    client_name = order.unique_code or f"order-{order.id}"
    requested_expires_at = wg_easy.compute_expires_at(period_days)

    # Fallback: если выбранный сервер забит/упал, пробуем все активные серверы из того же товара/страны.
    candidate_servers = [order.server_id]
    for product in runtime.get("products", []):
        if order.server_id in product.get("server_ids", []):
            for sid in product.get("server_ids", []):
                if sid not in candidate_servers:
                    candidate_servers.append(sid)

    last_error: Exception | None = None
    for server_id in candidate_servers:
        try:
            capacity = await wg_easy.get_server_capacity(server_id)
            if not capacity.get("sellable"):
                last_error = RuntimeError(f"{server_id}: нет свободных IP ({capacity})")
                continue

            client = await wg_easy.find_client(server_id, client_name)
            if not client:
                await wg_easy.create_client(server_id, client_name, requested_expires_at)
                client = await wg_easy.find_client(server_id, client_name)
            if not client:
                raise RuntimeError(f"WG-Easy client was not created: {client_name}")
            client_id = client.get("id")
            if not client_id:
                raise RuntimeError(f"WG-Easy client has no id: {client}")

            actual_expires_at = wg_easy.parse_wg_datetime(client.get("expiresAt"))
            config_text = await wg_easy.get_client_config(server_id, client_id)
            server_host = get_server(server_id)["url"]
            existing = crud_configs.get_by_unique_server(db, client_name, server_id)
            if existing:
                existing.config_text = config_text
                existing.expires_at = actual_expires_at
                existing.is_active = True
                existing.order_id = order.id
                existing.user_id = order.user_id or existing.user_id
                existing.config_name = client_name
                existing.server_host = server_host
                config = existing
            else:
                config = VpnConfig(
                    user_id=order.user_id,
                    order_id=order.id,
                    unique_code=client_name,
                    server_id=server_id,
                    config_name=client_name,
                    config_text=config_text,
                    server_host=server_host,
                    expires_at=actual_expires_at,
                    is_active=True,
                )
                db.add(config)
                db.flush()
            order.server_id = server_id
            order.config_id = config.id
            return config
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Не удалось выдать конфиг ни на одном сервере: {last_error}")


async def _renew_config(db: Session, order: Order) -> VpnConfig:
    runtime = get_runtime_with_db_servers()
    period_days = runtime["period_days"][order.period_key]
    config = crud_configs.get(db, order.config_id) if order.config_id else None
    if not config:
        raise RuntimeError("Config not found for renew")

    requested_expires_at = wg_easy.compute_expires_at(period_days, config.expires_at)
    client = await wg_easy.find_client(config.server_id, config.unique_code)
    if not client:
        raise RuntimeError(f"WG-Easy client not found for renew: {config.unique_code}")
    client_id = client.get("id")
    if not client_id:
        raise RuntimeError(f"WG-Easy client has no id: {client}")

    await wg_easy.update_client(config.server_id, client, expires_at=requested_expires_at, enabled=True, name=config.unique_code)
    fresh_client = await wg_easy.find_client(config.server_id, config.unique_code)
    if not fresh_client:
        raise RuntimeError(f"WG-Easy client not found after renew update: {config.unique_code}")
    actual_expires_at = wg_easy.parse_wg_datetime(fresh_client.get("expiresAt"))
    fresh_client_id = fresh_client.get("id") or client_id
    config.expires_at = actual_expires_at
    config.is_active = True
    config.order_id = order.id
    config.config_text = await wg_easy.get_client_config(config.server_id, fresh_client_id)
    return config


async def apply_paid_order(db: Session, order: Order) -> Order:
    # Идемпотентность: повторный callback/ручной запуск не создаст второй конфиг.
    if order.applied_at and order.config_id:
        order.status = OrderStatus.PAID.value
        db.commit()
        db.refresh(order)
        return order

    try:
        if order.action == OrderAction.PURCHASE.value:
            await _issue_purchase_config(db, order)
        elif order.action == OrderAction.RENEW.value:
            await _renew_config(db, order)
        else:
            raise RuntimeError("Unknown order action")

        now = datetime.now(timezone.utc)
        order.status = OrderStatus.PAID.value
        order.provider_status = ProviderStatus.CONFIRMED.value
        order.paid_at = order.paid_at or now
        order.applied_at = order.applied_at or now
        order.error_message = None
        db.commit()
        db.refresh(order)
        return order
    except Exception as exc:
        db.rollback()
        fresh = db.query(Order).filter(Order.id == order.id).first()
        if fresh:
            fresh.status = OrderStatus.ERROR.value
            fresh.provider_status = ProviderStatus.ERROR.value
            fresh.error_message = str(exc)[:4000]
            db.commit()
        raise


async def sync_ggsel_product_availability(product: dict, token: str | None = None) -> dict:
    server_id, checks = await select_best_server_for_product(product)
    enabled = bool(server_id)
    result = await ggsel.set_product_active(int(product["item_id"]), enabled, token=token)
    return {
        "enabled": enabled,
        "selected_server_id": server_id,
        "checks": checks,
        "ggsel": result,
    }


async def process_claim(db: Session, unique_code: str, attach_user_id: int | None = None):
    existing_claim = db.query(ClaimRecord).filter(ClaimRecord.unique_code == unique_code).first()
    if existing_claim:
        config = db.query(VpnConfig).filter(VpnConfig.id == existing_claim.config_id).first()
        if config and attach_user_id and not config.user_id:
            config.user_id = attach_user_id
            if existing_claim.order_id:
                order = db.query(Order).filter(Order.id == existing_claim.order_id).first()
                if order:
                    order.user_id = attach_user_id
            existing_claim.user_id = attach_user_id
            db.commit()
        return config, existing_claim, False

    token = await ggsel.generate_token()
    purchase = await ggsel.check_purchase(unique_code, token)
    state = purchase.get("unique_code_state", {}).get("state")
    if state not in PAID_STATES:
        raise RuntimeError("Покупка не оплачена или недоступна")

    product_id = int(purchase.get("id_goods"))
    product_route = get_product_by_item(product_id)
    if not product_route:
        raise RuntimeError("Товар не привязан к серверу")
    period_key = ggsel.detect_period_key(purchase)
    server_id, checks = await select_best_server_for_product(product_route)
    if not server_id:
        raise RuntimeError(f"Нет доступных серверов для товара {product_id}: {checks}")

    order = Order(
        user_id=attach_user_id,
        unique_code=unique_code,
        server_id=server_id,
        period_key=period_key,
        amount=0,
        status=OrderStatus.PAID.value,
        action=OrderAction.PURCHASE.value,
        source="ggsel_claim",
        provider="ggsel",
        provider_status=ProviderStatus.CONFIRMED.value,
    )
    db.add(order)
    db.flush()
    await apply_paid_order(db, order)
    db.refresh(order)

    claim = ClaimRecord(
        unique_code=unique_code,
        order_id=order.id,
        config_id=order.config_id,
        user_id=attach_user_id,
        status="processed",
        server_id=order.server_id,
        period_key=period_key,
    )
    db.add(claim)
    db.commit()

    try:
        await sync_ggsel_product_availability(product_route, token=token)
    except Exception:
        pass

    config = db.query(VpnConfig).filter(VpnConfig.id == order.config_id).first()
    return config, claim, True
