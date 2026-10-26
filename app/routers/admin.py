from datetime import datetime, timedelta
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_admin_user
from ..models import Order, User, VpnConfig
from ..services.auth import hash_password
from ..schemas import OrderOut, ConfigOut
from ..services.core import apply_paid_order, build_runtime_context

router = APIRouter(prefix='/admin-old')
templates = Jinja2Templates(directory='app/templates')


def redirect_to_admin(message: str = '', q: str = ''):
    suffix = ''
    params = []
    if message:
        params.append(f'message={quote_plus(message)}')
    if q:
        params.append(f'q={quote_plus(q)}')
    if params:
        suffix = '?' + '&'.join(params)
    return RedirectResponse(f'/admin-old{suffix}', status_code=303)


@router.get('', response_class=HTMLResponse)
async def admin_page(
    request: Request,
    q: str = '',
    message: str = '',
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    user_query = db.query(User)
    order_query = db.query(Order)
    config_query = db.query(VpnConfig)

    if q:
        like_q = f'%{q.strip()}%'
        user_query = user_query.filter(
            or_(User.username.ilike(like_q), User.telegram_id.ilike(like_q))
        )
        config_query = config_query.filter(
            or_(VpnConfig.config_name.ilike(like_q), VpnConfig.unique_code.ilike(like_q), VpnConfig.server_id.ilike(like_q))
        )
        try:
            q_id = int(q)
            order_query = order_query.filter(or_(Order.id == q_id, Order.user_id == q_id, Order.config_id == q_id))
        except ValueError:
            order_query = order_query.filter(
                or_(Order.unique_code.ilike(like_q), Order.server_id.ilike(like_q), Order.status.ilike(like_q), Order.action.ilike(like_q))
            )

    users = user_query.order_by(User.id.desc()).all()
    orders = order_query.order_by(Order.id.desc()).limit(200).all()
    configs = config_query.order_by(VpnConfig.id.desc()).limit(200).all()

    return templates.TemplateResponse('admin.html', {
        'request': request,
        'runtime': await build_runtime_context(),
        'users': users,
        'orders': orders,
        'configs': configs,
        'q': q,
        'message': message,
        'now': datetime.utcnow(),
    })


@router.get('/orders', response_model=list[OrderOut])
def admin_orders_api(
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    return db.query(Order).order_by(Order.id.desc()).limit(500).all()


@router.get('/configs', response_model=list[ConfigOut])
def admin_configs_api(
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    return db.query(VpnConfig).order_by(VpnConfig.id.desc()).limit(500).all()


@router.post('/users/{user_id}/password')
def admin_change_user_password(
    user_id: int,
    new_password: str = Form(...),
    q: str = Form(default=''),
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return redirect_to_admin('Пользователь не найден', q)
    if len(new_password) < 6:
        return redirect_to_admin('Новый пароль должен быть не короче 6 символов', q)
    user.password_hash = hash_password(new_password)
    db.commit()
    return redirect_to_admin(f'Пароль пользователя {user.username} обновлен', q)


@router.post('/configs/{config_id}/transfer')
def admin_transfer_config(
    config_id: int,
    username: str = Form(...),
    q: str = Form(default=''),
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    config = db.query(VpnConfig).filter(VpnConfig.id == config_id).first()
    new_user = db.query(User).filter(User.username == username.strip()).first()
    if not config:
        return redirect_to_admin('Конфиг не найден', q)
    if not new_user:
        return redirect_to_admin('Пользователь для переноса не найден', q)

    config.user_id = new_user.id
    if config.order_id:
        order = db.query(Order).filter(Order.id == config.order_id).first()
        if order:
            order.user_id = new_user.id
    db.commit()
    return redirect_to_admin(f'Конфиг #{config.id} перенесен пользователю {new_user.username}', q)


@router.post('/configs/{config_id}/extend')
def admin_extend_config(
    config_id: int,
    days: int = Form(...),
    q: str = Form(default=''),
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    config = db.query(VpnConfig).filter(VpnConfig.id == config_id).first()
    if not config:
        return redirect_to_admin('Конфиг не найден', q)
    if days == 0:
        return redirect_to_admin('Нужно указать количество дней', q)

    base_dt = config.expires_at if config.expires_at and config.expires_at > datetime.utcnow() else datetime.utcnow()
    config.expires_at = base_dt + timedelta(days=days)
    config.is_active = True
    db.commit()
    return redirect_to_admin(f'Срок конфига #{config.id} изменен на {days} дн.', q)


@router.post('/configs/{config_id}/toggle')
def admin_toggle_config(
    config_id: int,
    q: str = Form(default=''),
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    config = db.query(VpnConfig).filter(VpnConfig.id == config_id).first()
    if not config:
        return redirect_to_admin('Конфиг не найден', q)
    config.is_active = not config.is_active
    db.commit()
    state = 'активирован' if config.is_active else 'деактивирован'
    return redirect_to_admin(f'Конфиг #{config.id} {state}', q)


@router.post('/orders/{order_id}/mark-paid')
async def admin_mark_order_paid(
    order_id: int,
    q: str = Form(default=''),
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return redirect_to_admin('Заказ не найден', q)
    order.status = 'paid'
    order.paid_at = datetime.utcnow()
    try:
        await apply_paid_order(db, order)
    except Exception as exc:
        return redirect_to_admin(f'Заказ #{order.id} отмечен paid, но выдача не прошла: {exc}', q)
    return redirect_to_admin(f'Заказ #{order.id} отмечен как paid и применен', q)


@router.post('/orders/{order_id}/cancel')
def admin_cancel_order(
    order_id: int,
    q: str = Form(default=''),
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return redirect_to_admin('Заказ не найден', q)
    order.status = 'canceled'
    db.commit()
    return redirect_to_admin(f'Заказ #{order.id} отменен', q)
