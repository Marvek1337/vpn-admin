from __future__ import annotations

from datetime import datetime, timedelta
import json

from fastapi import APIRouter, Depends, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_admin_user
from app.models import User, Order, VpnConfig, VpnServer, ServerStat, AdminAuditLog, AppSetting, ProductRoute, SubscriptionPeriod
from app.services.auth import hash_password
from app.services.server_registry import audit
from app.services import wg_easy
from app.services.cleanup import cleanup_expired_clients
from app.services.legacy_import import import_legacy_sqlite
from app.services.admin_stats import build_admin_dashboard_stats
from app.settings import settings
from app.config import DEFAULT_PRIVACY_TEXT, DEFAULT_TERMS_TEXT, clear_runtime_config_cache

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")


def back(url: str, message: str | None = None):
    if message:
        sep = '&' if '?' in url else '?'
        return RedirectResponse(f"{url}{sep}message={message}", status_code=303)
    return RedirectResponse(url, status_code=303)


def _parse_server_ids(value: str) -> list[str]:
    result = []
    for raw in value.replace("\n", ",").split(","):
        server_id = raw.strip()
        if server_id and server_id not in result:
            result.append(server_id)
    return result


def _server_ids_text(value: str | None) -> str:
    try:
        raw = json.loads(value or "[]")
    except Exception:
        raw = []
    if not isinstance(raw, list):
        return ""
    return ", ".join(str(item) for item in raw if item)


def _set_app_setting(db: Session, key: str, value: str):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
        row.updated_at = datetime.utcnow()
    else:
        db.add(AppSetting(key=key, value=value))


def _settings_context(request: Request, admin: User, db: Session, message: str = "") -> dict:
    app_settings = {row.key: row.value for row in db.query(AppSetting).all()}
    app_settings.setdefault("privacy_text", DEFAULT_PRIVACY_TEXT)
    app_settings.setdefault("terms_text", DEFAULT_TERMS_TEXT)
    periods = db.query(SubscriptionPeriod).order_by(SubscriptionPeriod.sort_order.asc(), SubscriptionPeriod.id.asc()).all()
    products = db.query(ProductRoute).order_by(ProductRoute.id.asc()).all()
    product_server_ids = {item.id: _server_ids_text(item.server_ids) for item in products}
    servers = db.query(VpnServer).order_by(VpnServer.priority.asc(), VpnServer.id.asc()).all()
    return {
        "request": request,
        "admin": admin,
        "message": message,
        "app_settings": app_settings,
        "periods": periods,
        "products": products,
        "product_server_ids": product_server_ids,
        "servers": servers,
    }


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    stats = build_admin_dashboard_stats(db)
    latest_orders = db.query(Order).order_by(Order.id.desc()).limit(8).all()
    latest_configs = db.query(VpnConfig).order_by(VpnConfig.id.desc()).limit(8).all()
    servers = db.query(VpnServer).order_by(VpnServer.priority.asc()).all()
    return templates.TemplateResponse("admin_v2/dashboard.html", {
        "request": request, "admin": admin, "stats": stats, "orders": latest_orders,
        "configs": latest_configs, "servers": servers, "message": message,
        "users_count": stats["cards"]["users"], "orders_count": stats["cards"]["orders"],
        "configs_count": stats["cards"]["configs"], "servers_count": stats["cards"]["servers"],
    })


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, q: str = "", message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    query = db.query(User)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(User.username.ilike(like), User.telegram_id.ilike(like)))
    rows = query.order_by(User.id.desc()).limit(500).all()
    return templates.TemplateResponse("admin_v2/users.html", {"request": request, "admin": admin, "rows": rows, "q": q, "message": message})


@router.post("/users/{user_id}/password")
def set_user_password(request: Request, user_id: int, new_password: str = Form(...), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "user not found")
    if len(new_password) < 6:
        return back("/admin/users", "Пароль должен быть от 6 символов")
    user.password_hash = hash_password(new_password)
    db.commit()
    audit(db, admin.id, "user_password_changed", "user", str(user_id), request.client.host if request.client else None)
    return back("/admin/users", "Пароль обновлен")


@router.get("/orders", response_class=HTMLResponse)
def orders_page(request: Request, q: str = "", status: str = "", message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    query = db.query(Order)
    if status:
        query = query.filter(Order.status == status)
    if q:
        like = f"%{q.strip()}%"
        try:
            qid = int(q)
            query = query.filter(or_(Order.id == qid, Order.user_id == qid, Order.config_id == qid))
        except ValueError:
            query = query.filter(or_(Order.unique_code.ilike(like), Order.server_id.ilike(like), Order.provider_payment_id.ilike(like)))
    rows = query.order_by(Order.id.desc()).limit(500).all()
    return templates.TemplateResponse("admin_v2/orders.html", {"request": request, "admin": admin, "rows": rows, "q": q, "status": status, "message": message})


@router.get("/configs", response_class=HTMLResponse)
def configs_page(request: Request, q: str = "", active: str = "", message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    query = db.query(VpnConfig)
    if active == "1":
        query = query.filter(VpnConfig.is_active == True)  # noqa: E712
    elif active == "0":
        query = query.filter(VpnConfig.is_active == False)  # noqa: E712
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(VpnConfig.unique_code.ilike(like), VpnConfig.config_name.ilike(like), VpnConfig.server_id.ilike(like), VpnConfig.user_note.ilike(like)))
    rows = query.order_by(VpnConfig.id.desc()).limit(500).all()
    return templates.TemplateResponse("admin_v2/configs.html", {"request": request, "admin": admin, "rows": rows, "q": q, "active": active, "message": message})


@router.post("/configs/{config_id}/toggle")
def config_toggle(request: Request, config_id: int, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    c = db.query(VpnConfig).filter(VpnConfig.id == config_id).first()
    if not c:
        raise HTTPException(404, "config not found")
    c.is_active = not c.is_active
    db.commit()
    audit(db, admin.id, "config_toggle", "config", str(config_id), request.client.host if request.client else None, json.dumps({"active": c.is_active}))
    return back("/admin/configs", "Статус конфига изменен")


@router.post("/configs/{config_id}/extend")
def config_extend(request: Request, config_id: int, days: int = Form(...), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    c = db.query(VpnConfig).filter(VpnConfig.id == config_id).first()
    if not c:
        raise HTTPException(404, "config not found")
    base = c.expires_at if c.expires_at and c.expires_at > datetime.utcnow() else datetime.utcnow()
    c.expires_at = base + timedelta(days=days)
    c.is_active = True
    db.commit()
    audit(db, admin.id, "config_extend", "config", str(config_id), request.client.host if request.client else None, json.dumps({"days": days}))
    return back("/admin/configs", "Срок изменен")


@router.get("/servers", response_class=HTMLResponse)
def servers_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    rows = db.query(VpnServer).order_by(VpnServer.priority.asc(), VpnServer.id.asc()).all()
    latest_stats = {}
    for stat in db.query(ServerStat).order_by(ServerStat.id.desc()).limit(300).all():
        latest_stats.setdefault(stat.server_code, stat)
    return templates.TemplateResponse("admin_v2/servers.html", {
        "request": request,
        "admin": admin,
        "rows": rows,
        "message": message,
        "latest_stats": latest_stats,
        "grace_days": settings.expired_config_grace_days,
    })


@router.post("/servers/create")
def server_create(request: Request, code: str = Form(...), name: str = Form(...), protocol: str = Form("wg_easy"), country: str = Form(""), api_url: str = Form(""), server_host: str = Form(""), username: str = Form(""), password: str = Form(""), api_token: str = Form(""), subnet: str = Form(""), min_free_ips: int = Form(3), priority: int = Form(100), is_active: int = Form(1), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    code = code.strip()
    if db.query(VpnServer).filter(VpnServer.code == code).first():
        return back("/admin/servers", "Сервер с таким code уже есть")
    protocol = "wg_easy"
    row = VpnServer(code=code, name=name.strip(), protocol=protocol, country=country or None, api_url=api_url or None, panel_url=api_url or None, server_host=server_host or None, username=username or None, password=password or None, api_token=api_token or None, subnet=subnet or None, min_free_ips=min_free_ips, priority=priority, is_active=bool(is_active))
    db.add(row); db.commit()
    audit(db, admin.id, "server_create", "server", code, request.client.host if request.client else None)
    return back("/admin/servers", "Сервер добавлен")


@router.post("/servers/{server_id}/update")
def server_update(request: Request, server_id: int, name: str = Form(...), protocol: str = Form(...), country: str = Form(""), api_url: str = Form(""), server_host: str = Form(""), username: str = Form(""), password: str = Form(""), api_token: str = Form(""), subnet: str = Form(""), min_free_ips: int = Form(3), priority: int = Form(100), is_active: int = Form(0), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    row = db.query(VpnServer).filter(VpnServer.id == server_id).first()
    if not row:
        raise HTTPException(404, "server not found")
    protocol = "wg_easy"
    row.name=name; row.protocol=protocol; row.country=country or None; row.api_url=api_url or None; row.panel_url=api_url or None; row.server_host=server_host or None; row.username=username or None
    if password:
        row.password=password
    if api_token:
        row.api_token=api_token
    row.subnet=subnet or None; row.min_free_ips=min_free_ips; row.priority=priority; row.is_active=bool(is_active)
    row.updated_at=datetime.utcnow(); db.commit()
    audit(db, admin.id, "server_update", "server", row.code, request.client.host if request.client else None)
    return back("/admin/servers", "Сервер обновлен")


@router.post("/servers/{server_id}/delete")
def server_delete(request: Request, server_id: int, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    row = db.query(VpnServer).filter(VpnServer.id == server_id).first()
    if not row:
        raise HTTPException(404, "server not found")
    code = row.code
    has_configs = db.query(VpnConfig).filter(VpnConfig.server_id == code).first()
    if has_configs:
        row.is_active = False
        row.updated_at = datetime.utcnow()
        db.commit()
        audit(db, admin.id, "server_disable_with_configs", "server", code, request.client.host if request.client else None)
        return back("/admin/servers", "У сервера есть конфиги, поэтому он отключен без удаления")
    db.delete(row)
    db.commit()
    audit(db, admin.id, "server_delete", "server", code, request.client.host if request.client else None)
    return back("/admin/servers", "Сервер удален")


async def _save_server_stat(db: Session, row: VpnServer) -> dict:
    online = False
    error = None
    total = 0
    free_ips = None
    try:
        if row.protocol != "wg_easy":
            raise RuntimeError("Поддерживается только WG-Easy")
        capacity = await wg_easy.get_server_capacity(row.code)
        online = True
        total = int(capacity.get("clients_total") or 0)
        free_ips = capacity.get("free_count")
        if not capacity.get("sellable"):
            error = capacity.get("reason")
    except Exception as exc:
        error = str(exc)
    db.add(ServerStat(server_code=row.code, protocol=row.protocol, online=online, total_clients=total, active_clients=total, free_ips=free_ips, error=error, created_at=datetime.utcnow()))
    return {"online": online, "error": error, "free_ips": free_ips}


@router.post("/servers/{server_id}/check")
async def server_check(request: Request, server_id: int, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    row = db.query(VpnServer).filter(VpnServer.id == server_id).first()
    if not row:
        raise HTTPException(404, "server not found")
    result = await _save_server_stat(db, row)
    db.commit()
    audit(db, admin.id, "server_check", "server", row.code, request.client.host if request.client else None, json.dumps(result))
    return back("/admin/servers", "Проверка выполнена")


@router.post("/servers/check-all")
async def servers_check_all(request: Request, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    rows = db.query(VpnServer).filter(VpnServer.is_active == True).order_by(VpnServer.priority.asc()).all()  # noqa: E712
    checked = 0
    errors = 0
    for row in rows:
        result = await _save_server_stat(db, row)
        checked += 1
        if result.get("error"):
            errors += 1
    db.commit()
    audit(db, admin.id, "servers_check_all", "server", None, request.client.host if request.client else None, json.dumps({"checked": checked, "errors": errors}))
    return back("/admin/servers", f"Проверено серверов: {checked}, с ошибками: {errors}")


@router.post("/servers/{server_id}/cleanup")
async def server_cleanup(request: Request, server_id: int, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    row = db.query(VpnServer).filter(VpnServer.id == server_id).first()
    if not row:
        raise HTTPException(404, "server not found")
    result = await cleanup_expired_clients(db, row)
    audit(db, admin.id, "server_cleanup", "server", row.code, request.client.host if request.client else None, json.dumps(result, ensure_ascii=False))
    return back("/admin/servers", f"Очистка: удалено {result['deleted']} из {result['checked']}, grace {settings.expired_config_grace_days} дн.")


@router.post("/servers/cleanup-expired")
async def servers_cleanup_expired(request: Request, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    result = await cleanup_expired_clients(db)
    audit(db, admin.id, "servers_cleanup_expired", "server", None, request.client.host if request.client else None, json.dumps(result, ensure_ascii=False))
    return back("/admin/servers", f"Очистка: серверов {result['servers']}, удалено {result['deleted']} из {result['checked']}, grace {settings.expired_config_grace_days} дн.")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_overview.html", _settings_context(request, admin, db, message))


@router.get("/settings/app", response_class=HTMLResponse)
def settings_app_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_app.html", _settings_context(request, admin, db, message))


@router.get("/settings/ggsel", response_class=HTMLResponse)
def settings_ggsel_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_ggsel.html", _settings_context(request, admin, db, message))


@router.get("/settings/payments", response_class=HTMLResponse)
def settings_payments_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_payments.html", _settings_context(request, admin, db, message))


@router.get("/settings/telegram", response_class=HTMLResponse)
def settings_telegram_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_telegram.html", _settings_context(request, admin, db, message))


@router.get("/settings/operations", response_class=HTMLResponse)
def settings_operations_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_operations.html", _settings_context(request, admin, db, message))


@router.get("/settings/import", response_class=HTMLResponse)
def settings_import_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_import.html", _settings_context(request, admin, db, message))


@router.get("/settings/legal", response_class=HTMLResponse)
def settings_legal_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_legal.html", _settings_context(request, admin, db, message))


@router.get("/settings/periods", response_class=HTMLResponse)
def settings_periods_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_periods.html", _settings_context(request, admin, db, message))


@router.get("/settings/products", response_class=HTMLResponse)
def settings_products_page(request: Request, message: str = "", db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin_v2/settings_products.html", _settings_context(request, admin, db, message))


@router.post("/settings/app")
def settings_app_update(request: Request, brand: str = Form(...), support_url: str = Form(""), public_base_url: str = Form(""), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    _set_app_setting(db, "brand", brand.strip())
    _set_app_setting(db, "support_url", support_url.strip())
    _set_app_setting(db, "public_base_url", public_base_url.strip())
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "settings_app_update", "settings", "app", request.client.host if request.client else None)
    return back("/admin/settings/app", "Основные настройки сохранены")


@router.post("/settings/ggsel")
def settings_ggsel_update(
    request: Request,
    ggsel_base_url: str = Form(""),
    ggsel_seller_id: str = Form(""),
    ggsel_api_key: str = Form(""),
    ggsel_product_update_endpoint: str = Form(""),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    values = {
        "ggsel_base_url": ggsel_base_url.strip(),
        "ggsel_seller_id": ggsel_seller_id.strip(),
        "ggsel_api_key": ggsel_api_key.strip(),
        "ggsel_product_update_endpoint": ggsel_product_update_endpoint.strip(),
    }
    for key, value in values.items():
        _set_app_setting(db, key, value)
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "settings_ggsel_update", "settings", "ggsel", request.client.host if request.client else None)
    return back("/admin/settings/ggsel", "GGSEL настройки сохранены")


@router.post("/settings/payments")
def settings_payments_update(
    request: Request,
    platega_enabled: int = Form(0),
    platega_base_url: str = Form(""),
    platega_merchant_id: str = Form(""),
    platega_secret: str = Form(""),
    platega_payment_method: int = Form(2),
    platega_currency: str = Form("RUB"),
    platega_callback_secret: str = Form(""),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    values = {
        "platega_enabled": "true" if platega_enabled else "false",
        "platega_base_url": platega_base_url.strip(),
        "platega_merchant_id": platega_merchant_id.strip(),
        "platega_secret": platega_secret.strip(),
        "platega_payment_method": str(platega_payment_method),
        "platega_currency": platega_currency.strip() or "RUB",
        "platega_callback_secret": platega_callback_secret.strip(),
    }
    for key, value in values.items():
        _set_app_setting(db, key, value)
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "settings_payments_update", "settings", "payments", request.client.host if request.client else None)
    return back("/admin/settings/payments", "Платежные настройки сохранены")


@router.post("/settings/integrations")
def settings_integrations_update(
    request: Request,
    ggsel_base_url: str = Form(""),
    ggsel_seller_id: str = Form(""),
    ggsel_api_key: str = Form(""),
    ggsel_product_update_endpoint: str = Form(""),
    platega_enabled: int = Form(0),
    platega_base_url: str = Form(""),
    platega_merchant_id: str = Form(""),
    platega_secret: str = Form(""),
    platega_payment_method: int = Form(2),
    platega_currency: str = Form("RUB"),
    platega_callback_secret: str = Form(""),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    values = {
        "ggsel_base_url": ggsel_base_url.strip(),
        "ggsel_seller_id": ggsel_seller_id.strip(),
        "ggsel_api_key": ggsel_api_key.strip(),
        "ggsel_product_update_endpoint": ggsel_product_update_endpoint.strip(),
        "platega_enabled": "true" if platega_enabled else "false",
        "platega_base_url": platega_base_url.strip(),
        "platega_merchant_id": platega_merchant_id.strip(),
        "platega_secret": platega_secret.strip(),
        "platega_payment_method": str(platega_payment_method),
        "platega_currency": platega_currency.strip() or "RUB",
        "platega_callback_secret": platega_callback_secret.strip(),
    }
    for key, value in values.items():
        _set_app_setting(db, key, value)
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "settings_integrations_update", "settings", "integrations", request.client.host if request.client else None)
    return back("/admin/settings", "Интеграции сохранены")


@router.post("/settings/telegram")
def settings_telegram_update(
    request: Request,
    telegram_bot_token: str = Form(""),
    telegram_bot_username: str = Form(""),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    _set_app_setting(db, "telegram_bot_token", telegram_bot_token.strip())
    _set_app_setting(db, "telegram_bot_username", telegram_bot_username.strip().lstrip("@"))
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "settings_telegram_update", "settings", "telegram", request.client.host if request.client else None)
    return back("/admin/settings/telegram", "Telegram настройки сохранены")


@router.post("/settings/operations")
def settings_operations_update(request: Request, expired_config_grace_days: int = Form(1), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    _set_app_setting(db, "expired_config_grace_days", str(max(expired_config_grace_days, 0)))
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "settings_operations_update", "settings", "operations", request.client.host if request.client else None)
    return back("/admin/settings/operations", "Операционные настройки сохранены")


@router.post("/settings/legal")
def settings_legal_update(request: Request, privacy_text: str = Form(""), terms_text: str = Form(""), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    _set_app_setting(db, "privacy_text", privacy_text.strip())
    _set_app_setting(db, "terms_text", terms_text.strip())
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "settings_legal_update", "settings", "legal", request.client.host if request.client else None)
    return back("/admin/settings/legal", "Тексты документов сохранены")


@router.post("/settings/import-legacy-db")
def settings_import_legacy_db(
    request: Request,
    source_path: str = Form(...),
    import_users: int = Form(0),
    overwrite_configs: int = Form(0),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    try:
        result = import_legacy_sqlite(
            db,
            source_path=source_path.strip(),
            import_users=bool(import_users),
            overwrite_configs=bool(overwrite_configs),
        )
    except Exception as exc:
        return back("/admin/settings/import", f"Импорт не выполнен: {exc}")
    audit(db, admin.id, "legacy_db_import", "settings", "legacy_db", request.client.host if request.client else None, json.dumps(result, ensure_ascii=False))
    message = (
        f"Импорт: конфиги +{result['configs_created']}, обновлено {result['configs_updated']}, "
        f"пропущено {result['configs_skipped']}, пользователи +{result['users_created']}"
    )
    if result.get("missing_servers"):
        message += f"; нет серверов в настройках: {', '.join(result['missing_servers'])}"
    return back("/admin/settings/import", message)


def _parse_period_days(value: str) -> int | None:
    value = str(value or "").strip()
    if not value:
        return None
    return int(value)


@router.post("/settings/periods/create")
def period_create(request: Request, code: str = Form(...), label: str = Form(...), days: str = Form(""), price: float = Form(0), sort_order: int = Form(100), is_active: int = Form(1), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    code = code.strip()
    if db.query(SubscriptionPeriod).filter(SubscriptionPeriod.code == code).first():
        return back("/admin/settings/periods", "Период с таким кодом уже есть")
    db.add(SubscriptionPeriod(code=code, label=label.strip(), days=_parse_period_days(days), price=price, sort_order=sort_order, is_active=bool(is_active)))
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "period_create", "period", code, request.client.host if request.client else None)
    return back("/admin/settings/periods", "Период добавлен")


@router.post("/settings/periods/{period_id}/update")
def period_update(request: Request, period_id: int, code: str = Form(...), label: str = Form(...), days: str = Form(""), price: float = Form(0), sort_order: int = Form(100), is_active: int = Form(0), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    row = db.query(SubscriptionPeriod).filter(SubscriptionPeriod.id == period_id).first()
    if not row:
        raise HTTPException(404, "period not found")
    new_code = code.strip()
    exists = db.query(SubscriptionPeriod).filter(SubscriptionPeriod.code == new_code, SubscriptionPeriod.id != period_id).first()
    if exists:
        return back("/admin/settings/periods", "Период с таким кодом уже есть")
    row.code = new_code
    row.label = label.strip()
    row.days = _parse_period_days(days)
    row.price = price
    row.sort_order = sort_order
    row.is_active = bool(is_active)
    row.updated_at = datetime.utcnow()
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "period_update", "period", row.code, request.client.host if request.client else None)
    return back("/admin/settings/periods", "Период сохранен")


@router.post("/settings/periods/{period_id}/delete")
def period_delete(request: Request, period_id: int, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    row = db.query(SubscriptionPeriod).filter(SubscriptionPeriod.id == period_id).first()
    if not row:
        raise HTTPException(404, "period not found")
    code = row.code
    if db.query(Order).filter(Order.period_key == code).first():
        row.is_active = False
        row.updated_at = datetime.utcnow()
        db.commit()
        message = "Период используется в заказах, поэтому он отключен"
    else:
        db.delete(row)
        db.commit()
        message = "Период удален"
    clear_runtime_config_cache()
    audit(db, admin.id, "period_delete", "period", code, request.client.host if request.client else None)
    return back("/admin/settings/periods", message)


@router.post("/settings/products/create")
def product_create(request: Request, item_id: int = Form(...), name: str = Form(...), server_ids: str = Form(""), is_active: int = Form(1), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    if db.query(ProductRoute).filter(ProductRoute.item_id == item_id).first():
        return back("/admin/settings/products", "Товар с таким item_id уже есть")
    db.add(ProductRoute(
        item_id=item_id,
        name=name.strip(),
        server_ids=json.dumps(_parse_server_ids(server_ids), ensure_ascii=False),
        is_active=bool(is_active),
    ))
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "product_create", "product", str(item_id), request.client.host if request.client else None)
    return back("/admin/settings/products", "Товар добавлен")


@router.post("/settings/products/{product_id}/update")
def product_update(request: Request, product_id: int, item_id: int = Form(...), name: str = Form(...), server_ids: str = Form(""), is_active: int = Form(0), db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    row = db.query(ProductRoute).filter(ProductRoute.id == product_id).first()
    if not row:
        raise HTTPException(404, "product not found")
    exists = db.query(ProductRoute).filter(ProductRoute.item_id == item_id, ProductRoute.id != product_id).first()
    if exists:
        return back("/admin/settings/products", "Товар с таким item_id уже есть")
    row.item_id = item_id
    row.name = name.strip()
    row.server_ids = json.dumps(_parse_server_ids(server_ids), ensure_ascii=False)
    row.is_active = bool(is_active)
    row.updated_at = datetime.utcnow()
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "product_update", "product", str(item_id), request.client.host if request.client else None)
    return back("/admin/settings/products", "Товар сохранен")


@router.post("/settings/products/{product_id}/delete")
def product_delete(request: Request, product_id: int, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    row = db.query(ProductRoute).filter(ProductRoute.id == product_id).first()
    if not row:
        raise HTTPException(404, "product not found")
    item_id = row.item_id
    db.delete(row)
    db.commit()
    clear_runtime_config_cache()
    audit(db, admin.id, "product_delete", "product", str(item_id), request.client.host if request.client else None)
    return back("/admin/settings/products", "Товар удален")


@router.get("/security", response_class=HTMLResponse)
def security_page(request: Request, db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    logs = db.query(AdminAuditLog).order_by(AdminAuditLog.id.desc()).limit(200).all()
    return templates.TemplateResponse("admin_v2/security.html", {"request": request, "admin": admin, "logs": logs})


@router.get("/api/stats")
def api_stats(db: Session = Depends(get_db), admin: User = Depends(get_admin_user)):
    return JSONResponse({
        "users": db.query(User).count(),
        "orders": db.query(Order).count(),
        "paid_orders": db.query(Order).filter(Order.status == "paid").count(),
        "configs": db.query(VpnConfig).count(),
        "servers": db.query(VpnServer).count(),
    })
