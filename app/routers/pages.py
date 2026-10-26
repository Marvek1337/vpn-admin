from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..database import get_db
from ..deps import get_current_user, get_current_user_optional
from ..models import Order, User, VpnConfig, VpnServer
from ..core.statuses import OrderStatus
from ..crud import configs as crud_configs, orders as crud_orders, payment_logs as crud_payment_logs
from ..services.core import apply_paid_order, build_runtime_context, process_claim
from ..services.server_ping import measure_user_visible_pings
from ..services.amnezia_wg import build_amnezia_config
from ..services.payment import verify_callback
from ..services.qr import make_qr_data_uri
from ..services.redirects import safe_next_url
from ..settings import settings
from ..config import get_runtime_config

router = APIRouter()
templates = Jinja2Templates(directory='app/templates')


@router.get('/', response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse('home.html', {'request': request, 'runtime': await build_runtime_context()})


@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request, next: str = '/cabinet', error: str = ''):
    return templates.TemplateResponse('login.html', {'request': request, 'next': safe_next_url(next), 'error': error})


@router.get('/password/telegram', response_class=HTMLResponse)
def telegram_password_page(request: Request, username: str = '', sent: str = '', error: str = ''):
    return templates.TemplateResponse('password_telegram.html', {
        'request': request,
        'username': username,
        'sent': sent,
        'error': error,
    })


@router.get('/register', response_class=HTMLResponse)
def register_page(request: Request, next: str = '/cabinet', error: str = ''):
    return templates.TemplateResponse('register.html', {'request': request, 'next': safe_next_url(next), 'error': error})


@router.get('/api/servers/ping')
async def user_server_ping(current_user: User = Depends(get_current_user)):
    return JSONResponse(measure_user_visible_pings())


@router.get('/cabinet', response_class=HTMLResponse)
async def cabinet_page(
    request: Request,
    attached: int = 0,
    paid: int = 0,
    open_payment_for: int = 0,
    profile_saved: int = 0,
    note_saved: int = 0,
    telegram_saved: int = 0,
    telegram_code: str = '',
    profile_error: str = '',
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime

    orders = crud_orders.list_for_user(db, current_user.id)
    configs = crud_configs.list_for_user(db, current_user.id)
    runtime_context = await build_runtime_context()

    from datetime import timedelta

    grace_days = max(int(runtime_context.get("expired_config_grace_days", settings.expired_config_grace_days)), 0)
    grace_until = datetime.utcnow() - timedelta(days=grace_days)

    def config_sort_key(c):
        exp = getattr(c, "expires_at", None)
        if not exp:
            return datetime.max
        if isinstance(exp, datetime):
            return exp
        try:
            return datetime.fromisoformat(str(exp).replace("Z", "")[:19])
        except Exception:
            return datetime.max

    configs = [
        c for c in configs
        if getattr(c, "is_active", False)
        and (
            not getattr(c, "expires_at", None)
            or config_sort_key(c) >= grace_until
        )
    ]

    configs = sorted(configs, key=config_sort_key)

    return templates.TemplateResponse('cabinet.html', {
        'request': request,
        'user': current_user,
        'orders': orders,
        'configs': configs,
        'runtime': runtime_context,
        'now': datetime.utcnow(),
        'attached': attached,
        'paid': paid,
        'open_payment_for': open_payment_for,
        'profile_saved': profile_saved,
        'note_saved': note_saved,
        'telegram_saved': telegram_saved,
        'telegram_code': telegram_code,
        'profile_error': profile_error,
    })


@router.get('/privacy', response_class=HTMLResponse)
def privacy_page(request: Request):
    return templates.TemplateResponse('privacy.html', {'request': request, 'now': datetime.now(), 'runtime': get_runtime_config()})


@router.get('/terms', response_class=HTMLResponse)
def terms_page(request: Request):
    return templates.TemplateResponse('terms.html', {'request': request, 'now': datetime.now(), 'runtime': get_runtime_config()})


@router.get('/claim', response_class=HTMLResponse)
async def claim_page(
    request: Request,
    unique_code: str = Query(..., alias='uniquecode'),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    try:
        config, claim, created = await process_claim(db, unique_code, attach_user_id=current_user.id if current_user else None)
    except RuntimeError as exc:
        detail = str(exc)
        if "credentials" in detail.lower() or "token" in detail.lower():
            detail = "Сервис выдачи временно не настроен. Обратитесь в поддержку."
        raise HTTPException(status_code=400, detail=detail)
    if not config:
        raise HTTPException(status_code=404, detail='Config not found')
    request.session['claim_unique_code'] = unique_code
    runtime_context = await build_runtime_context()
    server = db.query(VpnServer).filter(VpnServer.code == config.server_id).first()
    server_name = server.name if server else runtime_context.get("server_names", {}).get(config.server_id)
    server_country = server.country if server else None
    qr = make_qr_data_uri(config.config_text)
    amnezia = build_amnezia_config(config.config_text, config.server_id, server_name, server_country)
    amnezia_qr = make_qr_data_uri(amnezia.text) if amnezia.available and amnezia.text else None
    return templates.TemplateResponse('claim.html', {
        'request': request,
        'config': config,
        'qr': qr,
        'amnezia': amnezia,
        'amnezia_qr': amnezia_qr,
        'current_user': current_user,
        'claim_created': created,
        'unique_code': unique_code,
        'runtime': runtime_context,
    })


@router.get('/claim/download')
def claim_download(unique_code: str, request: Request, db: Session = Depends(get_db)):
    claim_code = request.session.get('claim_unique_code')
    if not claim_code or claim_code != unique_code:
        raise HTTPException(status_code=403, detail='Access denied')
    config = db.query(VpnConfig).filter(VpnConfig.unique_code == unique_code).order_by(VpnConfig.id.desc()).first()
    if not config:
        raise HTTPException(status_code=404, detail='Config not found')
    return Response(config.config_text, media_type='application/octet-stream', headers={
        'Content-Disposition': 'attachment; filename="wgconfig.conf"',
        'Cache-Control': 'no-store',
    })


@router.get('/claim/download/amnezia')
def claim_amnezia_download(unique_code: str, request: Request, db: Session = Depends(get_db)):
    claim_code = request.session.get('claim_unique_code')
    if not claim_code or claim_code != unique_code:
        raise HTTPException(status_code=403, detail='Access denied')
    config = db.query(VpnConfig).filter(VpnConfig.unique_code == unique_code).order_by(VpnConfig.id.desc()).first()
    if not config:
        raise HTTPException(status_code=404, detail='Config not found')
    server = db.query(VpnServer).filter(VpnServer.code == config.server_id).first()
    amnezia = build_amnezia_config(
        config.config_text,
        config.server_id,
        server.name if server else None,
        server.country if server else None,
    )
    if not amnezia.available or not amnezia.text:
        raise HTTPException(status_code=404, detail='Amnezia WG endpoint is not configured for this server')
    return Response(amnezia.text, media_type='application/octet-stream', headers={
        'Content-Disposition': 'attachment; filename="amnezia-wg.conf"',
        'Cache-Control': 'no-store',
    })


@router.get('/claim/attach')
async def claim_attach(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    unique_code = request.session.get('claim_unique_code')
    if not unique_code:
        return RedirectResponse('/cabinet', status_code=303)
    await process_claim(db, unique_code, attach_user_id=current_user.id)
    return RedirectResponse('/cabinet?attached=1', status_code=303)


@router.get('/payments/mock/{order_id}')
async def mock_payment(order_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if (settings.app_env == "prod" or not settings.allow_test_payments
            or get_runtime_config().get("platega", {}).get("enabled")):
        raise HTTPException(status_code=404, detail='Payment endpoint not found')
    order = crud_orders.get_for_user(db, order_id, current_user.id)
    if not order:
        raise HTTPException(status_code=404, detail='Order not found')
    if order.status == OrderStatus.PAID.value and order.applied_at:
        return RedirectResponse('/cabinet?paid=1', status_code=303)
    order.status = OrderStatus.PAID.value
    await apply_paid_order(db, order)
    return RedirectResponse('/cabinet?paid=1', status_code=303)

@router.post('/payments/platega/callback')
async def platega_callback(request: Request, db: Session = Depends(get_db)):
    try:
        if not verify_callback(dict(request.headers)):
            raise HTTPException(status_code=403, detail='Invalid callback credentials')

        payload = await request.json()

        # === Telegram Bot Payments ===
        payment_payload = payload.get('payload') or payload.get('orderId')

        if payment_payload and str(payment_payload).startswith('bot_'):
            import httpx

            if not settings.bot_payment_callback_url:
                raise HTTPException(status_code=503, detail='Bot payment callback is not configured')
            bot_order_id = str(payment_payload).replace('bot_', '', 1)

            async with httpx.AsyncClient(timeout=20) as client:
                forwarded = await client.post(
                    settings.bot_payment_callback_url,
                    json={
                        'orderId': bot_order_id,
                        'status': payload.get('status'),
                        'transactionId': payload.get('transactionId'),
                        'payload': payment_payload,
                    }
                )
                forwarded.raise_for_status()

            return JSONResponse({
                'ok': True,
                'forwarded_to_bot': True
            })

        # === Main Site Payments ===
        transaction_id = payload.get('transactionId') or payload.get('id')
        status = payload.get('status')

        if not transaction_id or not status:
            raise HTTPException(status_code=400, detail='Invalid payload')

        order = crud_orders.get_by_payment_id(db, transaction_id)

        crud_payment_logs.create(
            db,
            order_id=order.id if order else None,
            provider='platega',
            provider_payment_id=transaction_id,
            status=status,
            payload=payload
        )

        if not order:
            db.commit()
            return JSONResponse({'ok': True})

        # Идемпотентность
        if order.status == OrderStatus.PAID.value and order.applied_at:
            order.provider_status = status
            db.commit()
            return JSONResponse({
                'ok': True,
                'idempotent': True
            })

        order.provider_status = status

        if status == 'CONFIRMED':
            order.status = OrderStatus.PAID.value
            await apply_paid_order(db, order)

        elif status in {'CANCELED', 'CHARGEBACKED'} and order.status != OrderStatus.PAID.value:
            order.status = OrderStatus.CANCELED.value
            db.commit()

        else:
            db.commit()

        return JSONResponse({'ok': True})

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail='Payment callback failed')
        
@router.get('/payments/result', response_class=HTMLResponse)
def payment_result(request: Request, order_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    order = crud_orders.get_for_user(db, order_id, current_user.id)
    if not order:
        raise HTTPException(status_code=404, detail='Order not found')
    return templates.TemplateResponse('payment_result.html', {'request': request, 'order': order})
