from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..core.statuses import OrderAction, OrderStatus
from ..crud import configs as crud_configs, orders as crud_orders
from ..services import wg_easy
from ..services.core import sync_ggsel_product_availability
from ..services.payment import create_platega_link
from ..services.server_registry import get_runtime_with_db_servers

router = APIRouter(prefix='/orders')


@router.post('/create')
async def create_order(
    server_id: str = Form(...),
    period_key: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    runtime = get_runtime_with_db_servers()
    if server_id not in runtime['server_names']:
        raise HTTPException(status_code=400, detail='Некорректный сервер')
    if period_key not in runtime['periods']:
        raise HTTPException(status_code=400, detail='Некорректный срок')

    try:
        capacity = await wg_easy.get_server_capacity(server_id)
    except Exception:
        raise HTTPException(status_code=400, detail='Сервер временно недоступен для проверки. Попробуйте другую локацию или повторите позже.')
    if not capacity.get('sellable'):
        raise HTTPException(status_code=400, detail=f"На сервере нет места. Свободно: {capacity.get('free_count')}, минимум: {capacity.get('min_free_ips')}")

    order = crud_orders.create(
        db,
        user_id=current_user.id,
        server_id=server_id,
        period_key=period_key,
        amount=runtime['period_prices'][period_key],
        unique_code=uuid4().hex,
        status=OrderStatus.NEW.value,
        action=OrderAction.PURCHASE.value,
        source='cabinet',
        provider='platega',
    )

    for product in runtime.get('products', []):
        if server_id in product.get('server_ids', []):
            try:
                await sync_ggsel_product_availability(product)
            except Exception:
                pass

    return RedirectResponse(url=f'/cabinet?open_payment_for={order.id}', status_code=303)


@router.post('/renew/{config_id}')
async def renew_order(
    config_id: int,
    period_key: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    runtime = get_runtime_with_db_servers()
    if period_key not in runtime['periods']:
        raise HTTPException(status_code=400, detail='Некорректный срок')
    config = crud_configs.get_for_user(db, config_id, current_user.id)
    if not config:
        raise HTTPException(status_code=404, detail='Конфиг не найден')
    order = crud_orders.create(
        db,
        user_id=current_user.id,
        config_id=config.id,
        server_id=config.server_id,
        period_key=period_key,
        amount=runtime['period_prices'][period_key],
        unique_code=uuid4().hex,
        status=OrderStatus.NEW.value,
        action=OrderAction.RENEW.value,
        source='cabinet',
        provider='platega',
    )
    return RedirectResponse(url=f'/cabinet?open_payment_for={order.id}', status_code=303)


@router.post('/{order_id}/payment-link')
async def create_order_payment_link(
    order_id: int,
    method: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed_methods = {'sbp_qr', 'card', 'crypto'}
    if method not in allowed_methods:
        raise HTTPException(status_code=400, detail='Некорректный способ оплаты')
    order = crud_orders.get_for_user(db, order_id, current_user.id)
    if not order:
        raise HTTPException(status_code=404, detail='Заказ не найден')
    if order.status != OrderStatus.NEW.value:
        raise HTTPException(status_code=400, detail='Заказ уже не доступен для оплаты')

    # Идемпотентность ссылки: если ссылка уже создана — отдаём её, не создаём второй платеж.
    if order.provider_payment_id and order.provider_payment_url:
        return JSONResponse({'redirect': order.provider_payment_url})

    try:
        payment = await create_platega_link(order, method)
    except Exception:
        raise HTTPException(status_code=400, detail='Не удалось создать платежную ссылку. Проверьте платежные настройки или повторите позже.')

    order.payment_method = method
    order.provider_payment_id = payment.get('transaction_id')
    order.provider_payment_url = payment.get('redirect')
    order.provider_status = payment.get('status')
    db.commit()
    return JSONResponse({'redirect': payment.get('redirect')})
