from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import DEFAULT_PRIVACY_TEXT, DEFAULT_TERMS_TEXT
from app.database import get_db
from app.services.installer import complete_install, is_installed

router = APIRouter(tags=["Install"])
templates = Jinja2Templates(directory="app/templates")


def _items(form, key: str) -> list[str]:
    return [str(item).strip() for item in form.getlist(key)]


def _parse_optional_int(value: str | None) -> int | None:
    value = str(value or "").strip()
    if not value:
        return None
    return int(value)


def _parse_int(value: str | None, default: int = 0) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError:
        return default


def _parse_float(value: str | None, default: float = 0) -> float:
    try:
        return float(str(value or "").replace(",", ".").strip())
    except ValueError:
        return default


def _split_server_ids(value: str) -> list[str]:
    result = []
    for raw in value.replace("\n", ",").split(","):
        server_id = raw.strip()
        if server_id and server_id not in result:
            result.append(server_id)
    return result


def _default_context(request: Request, error: str = "") -> dict:
    return {
        "request": request,
        "error": error,
        "default_periods": [
            {"code": "30", "label": "30 дней", "days": "30", "price": "49"},
            {"code": "90", "label": "90 дней", "days": "90", "price": "147"},
            {"code": "forever", "label": "Навсегда", "days": "", "price": "3549"},
        ],
        "default_servers": [
            {"code": "server-1", "name": "Main location", "api_url": "http://127.0.0.1:51821", "server_host": "", "username": "", "password": "", "subnet": "10.8.0.0/24", "country": ""},
        ],
        "default_products": [
            {"item_id": "", "name": "", "server_ids": "server-1"},
        ],
        "privacy_text": DEFAULT_PRIVACY_TEXT,
        "terms_text": DEFAULT_TERMS_TEXT,
    }


@router.get("/install", response_class=HTMLResponse)
def install_page(request: Request, db: Session = Depends(get_db)):
    if is_installed(db):
        return RedirectResponse("/admin", status_code=303)
    return templates.TemplateResponse("install.html", _default_context(request))


@router.post("/install")
async def install_submit(request: Request, db: Session = Depends(get_db)):
    if is_installed(db):
        return RedirectResponse("/admin", status_code=303)

    form = await request.form()
    admin_username = str(form.get("admin_username") or "").strip()
    admin_password = str(form.get("admin_password") or "")
    admin_password_repeat = str(form.get("admin_password_repeat") or "")
    if len(admin_username) < 3:
        return templates.TemplateResponse("install.html", _default_context(request, "Логин администратора должен быть от 3 символов"), status_code=400)
    if len(admin_password) < 8:
        return templates.TemplateResponse("install.html", _default_context(request, "Пароль администратора должен быть от 8 символов"), status_code=400)
    if admin_password != admin_password_repeat:
        return templates.TemplateResponse("install.html", _default_context(request, "Пароли администратора не совпадают"), status_code=400)

    period_codes = _items(form, "period_code")
    periods = []
    for idx, code in enumerate(period_codes):
        label = _items(form, "period_label")[idx] if idx < len(_items(form, "period_label")) else ""
        if not code and not label:
            continue
        periods.append({
            "code": code,
            "label": label or code,
            "days": _parse_optional_int((_items(form, "period_days")[idx] if idx < len(_items(form, "period_days")) else "")),
            "price": _parse_float((_items(form, "period_price")[idx] if idx < len(_items(form, "period_price")) else "0")),
        })
    if not periods:
        return templates.TemplateResponse("install.html", _default_context(request, "Добавьте хотя бы один тарифный период"), status_code=400)
    if len({item["code"] for item in periods}) != len(periods):
        return templates.TemplateResponse("install.html", _default_context(request, "Коды тарифных периодов должны быть уникальными"), status_code=400)

    server_codes = _items(form, "server_code")
    servers = []
    for idx, code in enumerate(server_codes):
        name = _items(form, "server_name")[idx] if idx < len(_items(form, "server_name")) else ""
        api_url = _items(form, "server_api_url")[idx] if idx < len(_items(form, "server_api_url")) else ""
        if not code and not name and not api_url:
            continue
        if not code or not name or not api_url:
            return templates.TemplateResponse("install.html", _default_context(request, "У каждого сервера должны быть code, название и WG-Easy URL"), status_code=400)
        servers.append({
            "code": code,
            "name": name,
            "api_url": api_url.rstrip("/"),
            "server_host": _items(form, "server_host")[idx] if idx < len(_items(form, "server_host")) else "",
            "username": _items(form, "server_username")[idx] if idx < len(_items(form, "server_username")) else "",
            "password": _items(form, "server_password")[idx] if idx < len(_items(form, "server_password")) else "",
            "subnet": _items(form, "server_subnet")[idx] if idx < len(_items(form, "server_subnet")) else "",
            "country": _items(form, "server_country")[idx] if idx < len(_items(form, "server_country")) else "",
            "min_free_ips": _parse_int((_items(form, "server_min_free_ips")[idx] if idx < len(_items(form, "server_min_free_ips")) else "3"), 3),
            "priority": _parse_int((_items(form, "server_priority")[idx] if idx < len(_items(form, "server_priority")) else "100"), 100),
        })
    if not servers:
        return templates.TemplateResponse("install.html", _default_context(request, "Добавьте хотя бы один WG-Easy сервер"), status_code=400)
    if len({item["code"] for item in servers}) != len(servers):
        return templates.TemplateResponse("install.html", _default_context(request, "Коды серверов должны быть уникальными"), status_code=400)

    products = []
    product_ids = _items(form, "product_item_id")
    for idx, raw_id in enumerate(product_ids):
        name = _items(form, "product_name")[idx] if idx < len(_items(form, "product_name")) else ""
        if not raw_id and not name:
            continue
        if not raw_id:
            return templates.TemplateResponse("install.html", _default_context(request, "У каждого GGSEL товара должен быть item_id"), status_code=400)
        try:
            item_id = int(raw_id)
        except ValueError:
            return templates.TemplateResponse("install.html", _default_context(request, "GGSEL item_id должен быть числом"), status_code=400)
        products.append({
            "item_id": item_id,
            "name": name or raw_id,
            "server_ids": _split_server_ids(_items(form, "product_server_ids")[idx] if idx < len(_items(form, "product_server_ids")) else ""),
        })
    if len({item["item_id"] for item in products}) != len(products):
        return templates.TemplateResponse("install.html", _default_context(request, "GGSEL item_id должны быть уникальными"), status_code=400)

    payload = {
        "admin_username": admin_username,
        "admin_password": admin_password,
        "settings": {
            "brand": str(form.get("brand") or "vpn-admin").strip(),
            "support_url": str(form.get("support_url") or "").strip(),
            "public_base_url": str(form.get("public_base_url") or "").strip(),
            "expired_config_grace_days": _parse_int(str(form.get("expired_config_grace_days") or "1"), 1),
            "ggsel_base_url": str(form.get("ggsel_base_url") or "https://seller.ggsel.com/api_sellers/api").strip(),
            "ggsel_seller_id": str(form.get("ggsel_seller_id") or "").strip(),
            "ggsel_api_key": str(form.get("ggsel_api_key") or "").strip(),
            "ggsel_product_update_endpoint": str(form.get("ggsel_product_update_endpoint") or "").strip(),
            "platega_enabled": "true" if form.get("platega_enabled") else "false",
            "platega_base_url": str(form.get("platega_base_url") or "https://app.platega.io").strip(),
            "platega_merchant_id": str(form.get("platega_merchant_id") or "").strip(),
            "platega_secret": str(form.get("platega_secret") or "").strip(),
            "platega_payment_method": _parse_int(str(form.get("platega_payment_method") or "2"), 2),
            "platega_currency": str(form.get("platega_currency") or "RUB").strip(),
            "platega_callback_secret": str(form.get("platega_callback_secret") or "").strip(),
            "telegram_bot_token": str(form.get("telegram_bot_token") or "").strip(),
            "telegram_bot_username": str(form.get("telegram_bot_username") or "").strip().lstrip("@"),
            "privacy_text": str(form.get("privacy_text") or DEFAULT_PRIVACY_TEXT).strip(),
            "terms_text": str(form.get("terms_text") or DEFAULT_TERMS_TEXT).strip(),
        },
        "periods": periods,
        "servers": servers,
        "products": products,
    }
    complete_install(db, payload)
    request.session.clear()
    return RedirectResponse("/login?next=/admin", status_code=303)
