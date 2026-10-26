import logging
from urllib.parse import quote

from sqlalchemy import text
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_500_INTERNAL_SERVER_ERROR
from .database import Base, engine, SessionLocal
from .routers import admin, auth, configs, orders, pages, monitoring, admin_v2, install
from .config import get_runtime_config
from .services.redirects import safe_next_url
from .services.installer import is_installed
from .settings import settings

app = FastAPI(title='vpn-admin')
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory='app/templates')
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=settings.app_env == "prod",
)

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / 'static'
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount('/static', StaticFiles(directory=str(STATIC_DIR)), name='static')


def _error_runtime() -> dict:
    try:
        runtime = get_runtime_config()
    except Exception:
        runtime = {}
    if not isinstance(runtime, dict):
        runtime = {}
    app_config = runtime.get("app") if isinstance(runtime, dict) else {}
    if not isinstance(app_config, dict):
        app_config = {}
    app_config.setdefault("brand", "vpn-admin")
    app_config.setdefault("support_url", "")
    runtime["app"] = app_config
    return runtime


def _is_json_request(request: Request) -> bool:
    path = request.url.path
    accept = request.headers.get("accept", "")
    content_type = request.headers.get("content-type", "")
    requested_with = request.headers.get("x-requested-with", "")
    api_like = (
        path == "/health"
        or path.startswith("/api/")
        or path.startswith("/admin/api")
        or path.startswith("/admin/monitoring/api")
        or path == "/configs/my"
        or (path.startswith("/configs/my/") and path.endswith("/qr"))
        or (path.startswith("/orders/") and path.endswith("/payment-link"))
        or path == "/payments/platega/callback"
    )
    return (
        api_like
        or "application/json" in content_type
        or requested_with.lower() == "xmlhttprequest"
        or ("application/json" in accept and "text/html" not in accept)
    )


def _error_text(status_code: int, detail: object = None) -> tuple[str, str]:
    messages = {
        400: ("Запрос не выполнен", "Проверьте данные и повторите действие."),
        401: ("Нужен вход", "Войдите в аккаунт, чтобы продолжить."),
        403: ("Доступ ограничен", "У аккаунта нет прав для этого действия."),
        404: ("Страница не найдена", "Проверьте адрес или вернитесь в личный кабинет."),
        405: ("Метод не поддерживается", "Эта страница не принимает такой тип запроса."),
        422: ("Некорректные данные", "Не хватает обязательных данных или одно из полей заполнено неверно."),
        500: ("Сервис временно недоступен", "Мы уже знаем об ошибке. Попробуйте повторить действие чуть позже."),
    }
    title, message = messages.get(status_code, ("Что-то пошло не так", "Попробуйте повторить действие или вернитесь назад."))

    if isinstance(detail, str) and status_code < 500:
        replacements = {
            "Bad Request": "Проверьте данные и повторите действие.",
            "Config not found": "Конфиг не найден.",
            "Forbidden": "У аккаунта нет прав для этого действия.",
            "Method Not Allowed": "Эта страница не принимает такой тип запроса.",
            "Not Found": "Проверьте адрес или вернитесь в личный кабинет.",
            "Order not found": "Заказ не найден.",
            "Unauthorized": "Войдите в аккаунт, чтобы продолжить.",
            "Access denied": "Доступ к этому файлу ограничен.",
            "Payment endpoint not found": "Платежная страница не найдена.",
            "user not found": "Пользователь не найден.",
            "config not found": "Конфиг не найден.",
            "server not found": "Сервер не найден.",
            "period not found": "Тариф не найден.",
            "product not found": "Товар не найден.",
        }
        message = replacements.get(detail, detail)
        if message and not message.endswith((".", "!", "?")):
            message += "."
    return title, message


def _error_response(request: Request, status_code: int, title: str, message: str):
    if _is_json_request(request):
        return JSONResponse({"detail": message}, status_code=status_code)
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "runtime": _error_runtime(),
            "status_code": status_code,
            "title": title,
            "message": message,
            "path": request.url.path,
        },
        status_code=status_code,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == HTTP_401_UNAUTHORIZED and not _is_json_request(request):
        next_url = safe_next_url(request.url.path)
        return RedirectResponse(f"/login?next={quote(next_url)}", status_code=303)
    title, message = _error_text(exc.status_code, getattr(exc, "detail", None))
    return _error_response(request, exc.status_code, title, message)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if _is_json_request(request):
        return JSONResponse({"detail": exc.errors()}, status_code=422)
    title, message = _error_text(422)
    return _error_response(request, 422, title, message)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled request error: %s %s", request.method, request.url.path)
    title, message = _error_text(HTTP_500_INTERNAL_SERVER_ERROR)
    return _error_response(request, HTTP_500_INTERNAL_SERVER_ERROR, title, message)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.app_env == "prod":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def require_installation(request: Request, call_next):
    path = request.url.path
    allowed_prefixes = ("/install", "/static")
    allowed_paths = {"/health", "/favicon.ico"}
    if path not in allowed_paths and not path.startswith(allowed_prefixes):
        db = SessionLocal()
        try:
            if not is_installed(db):
                return RedirectResponse("/install", status_code=303)
        finally:
            db.close()
    return await call_next(request)


def _sqlite_columns(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _sqlite_indexes(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA index_list({table})")).fetchall()
    return {row[1] for row in rows}


def ensure_sqlite_migrations():
    """Small SQLite migrations for installations upgraded from older builds."""
    if not str(settings.database_url).startswith('sqlite'):
        return

    with engine.begin() as conn:
        vpn_cols = _sqlite_columns(conn, 'vpn_configs')
        if 'user_note' not in vpn_cols:
            conn.execute(text('ALTER TABLE vpn_configs ADD COLUMN user_note TEXT'))

        order_cols = _sqlite_columns(conn, 'orders')
        if 'error_message' not in order_cols:
            conn.execute(text('ALTER TABLE orders ADD COLUMN error_message TEXT'))

        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS payment_logs (
                id INTEGER NOT NULL PRIMARY KEY,
                order_id INTEGER,
                provider VARCHAR(32) NOT NULL DEFAULT 'platega',
                provider_payment_id VARCHAR(128),
                status VARCHAR(64),
                payload TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(order_id) REFERENCES orders (id)
            )
        '''))

        indexes = _sqlite_indexes(conn, 'orders')
        if 'ix_orders_user_created' not in indexes:
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_orders_user_created ON orders (user_id, created_at)'))
        if 'ix_orders_status_created' not in indexes:
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_orders_status_created ON orders (status, created_at)'))

        cfg_indexes = _sqlite_indexes(conn, 'vpn_configs')
        if 'ix_vpn_configs_user_created' not in cfg_indexes:
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_vpn_configs_user_created ON vpn_configs (user_id, created_at)'))
        if 'ix_vpn_configs_active_expires' not in cfg_indexes:
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_vpn_configs_active_expires ON vpn_configs (is_active, expires_at)'))


        cfg_cols = _sqlite_columns(conn, 'vpn_configs')
        if 'protocol' not in cfg_cols:
            conn.execute(text("ALTER TABLE vpn_configs ADD COLUMN protocol VARCHAR(32) DEFAULT 'wireguard'"))
        if 'external_id' not in cfg_cols:
            conn.execute(text('ALTER TABLE vpn_configs ADD COLUMN external_id VARCHAR(128)'))
        if 'subscription_url' not in cfg_cols:
            conn.execute(text('ALTER TABLE vpn_configs ADD COLUMN subscription_url TEXT'))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS vpn_servers (
                id INTEGER NOT NULL PRIMARY KEY,
                code VARCHAR(64) NOT NULL UNIQUE,
                name VARCHAR(160) NOT NULL,
                country VARCHAR(80),
                protocol VARCHAR(32) NOT NULL DEFAULT 'wg_easy',
                panel_url VARCHAR(255),
                api_url VARCHAR(255),
                username VARCHAR(160),
                password TEXT,
                api_token TEXT,
                server_host VARCHAR(255),
                subnet VARCHAR(80),
                priority INTEGER NOT NULL DEFAULT 100,
                max_clients INTEGER NOT NULL DEFAULT 0,
                min_free_ips INTEGER NOT NULL DEFAULT 3,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_vpn_servers_code ON vpn_servers (code)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_vpn_servers_active_priority ON vpn_servers (is_active, priority)'))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS server_stats (
                id INTEGER NOT NULL PRIMARY KEY,
                server_code VARCHAR(64) NOT NULL,
                protocol VARCHAR(32) NOT NULL DEFAULT 'wg_easy',
                online BOOLEAN NOT NULL DEFAULT 0,
                total_clients INTEGER NOT NULL DEFAULT 0,
                active_clients INTEGER NOT NULL DEFAULT 0,
                free_ips INTEGER,
                error TEXT,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_server_stats_code_created ON server_stats (server_code, created_at)'))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER NOT NULL PRIMARY KEY,
                admin_id INTEGER,
                action VARCHAR(120) NOT NULL,
                entity_type VARCHAR(80),
                entity_id VARCHAR(80),
                ip_address VARCHAR(80),
                payload TEXT,
                created_at DATETIME NOT NULL
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_auth_codes (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                telegram_id VARCHAR(80),
                purpose VARCHAR(32) NOT NULL,
                code VARCHAR(32) NOT NULL,
                expires_at DATETIME NOT NULL,
                used_at DATETIME,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users (id)
            )
        """))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_telegram_auth_codes_user_purpose ON telegram_auth_codes (user_id, purpose)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_telegram_auth_codes_code_purpose ON telegram_auth_codes (code, purpose)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_telegram_auth_codes_telegram_id ON telegram_auth_codes (telegram_id)'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_telegram_auth_codes_expires_at ON telegram_auth_codes (expires_at)'))

        pl_indexes = _sqlite_indexes(conn, 'payment_logs')
        if 'ix_payment_logs_order_id' not in pl_indexes:
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_payment_logs_order_id ON payment_logs (order_id)'))
        if 'ix_payment_logs_provider_payment_id' not in pl_indexes:
            conn.execute(text('CREATE INDEX IF NOT EXISTS ix_payment_logs_provider_payment_id ON payment_logs (provider_payment_id)'))


@app.on_event('startup')
def on_startup():
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_migrations()


@app.get('/health')
def health():
    return {'ok': True}


@app.get('/favicon.ico', include_in_schema=False)
def favicon():
    return RedirectResponse('/static/favicon.svg', status_code=307)


@app.get('/admin/v2')
def admin_v2_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/admin', status_code=303)


@app.get('/admin/v2/{path:path}')
def admin_v2_redirect_path(path: str):
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/admin/' + path, status_code=303)


app.include_router(pages.router)
app.include_router(install.router)
app.include_router(auth.router)
app.include_router(orders.router)
app.include_router(configs.router)
app.include_router(admin.router)
app.include_router(monitoring.router)
app.include_router(admin_v2.router)
