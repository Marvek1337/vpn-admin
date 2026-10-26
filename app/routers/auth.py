from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..database import get_db
from ..crud import users as crud_users
from ..models import User
from ..schemas import TokenResponse
from ..services.auth import create_access_token, hash_password, verify_password
from ..services.redirects import safe_next_url
from ..services.telegram import create_telegram_code, consume_telegram_code, send_telegram_message

router = APIRouter()


def _redirect(url: str, **params: str):
    pairs = [f"{key}={quote_plus(str(value))}" for key, value in params.items() if value]
    if not pairs:
        return RedirectResponse(url=url, status_code=303)
    sep = "&" if "?" in url else "?"
    return RedirectResponse(url=f"{url}{sep}{'&'.join(pairs)}", status_code=303)


@router.post('/api/auth/token', response_model=TokenResponse)
def api_token(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = crud_users.get_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail='Неверный логин или пароль')
    return TokenResponse(
        access_token=create_access_token(user.id, user.is_admin),
        user_id=user.id,
        is_admin=user.is_admin,
    )


@router.post('/auth/register')
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    telegram_id: str = Form(default=''),
    next_url: str = Form(default='/cabinet'),
    db: Session = Depends(get_db),
):
    username = username.strip()
    next_url = safe_next_url(next_url)
    if len(username) < 3 or len(password) < 6:
        return _redirect('/register', error='Логин от 3 символов, пароль от 6 символов', next=next_url)
    if crud_users.get_by_username(db, username):
        return _redirect('/register', error='Пользователь уже существует', next=next_url)
    user = crud_users.create(db, username=username, password_hash=hash_password(password), telegram_id=telegram_id or None)
    request.session['user_id'] = user.id
    return RedirectResponse(url=next_url, status_code=303)


@router.post('/auth/login')
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_url: str = Form(default='/cabinet'),
    db: Session = Depends(get_db),
):
    next_url = safe_next_url(next_url)
    user = crud_users.get_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        return _redirect('/login', error='Неверный логин или пароль', next=next_url)
    request.session['user_id'] = user.id
    return RedirectResponse(url=next_url, status_code=303)


@router.get('/auth/logout')
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url='/', status_code=303)


@router.post('/auth/change-password')
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_repeat: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get('user_id')
    if not user_id:
        return RedirectResponse(url='/login?error=Нужно войти в аккаунт&next=/cabinet', status_code=303)
    user = crud_users.get(db, int(user_id))
    if not user:
        request.session.clear()
        return RedirectResponse(url='/login?error=Пользователь не найден&next=/cabinet', status_code=303)
    if not verify_password(current_password, user.password_hash):
        return RedirectResponse(url='/cabinet?profile_error=Неверный текущий пароль', status_code=303)
    if len(new_password) < 6:
        return RedirectResponse(url='/cabinet?profile_error=Новый пароль слишком короткий', status_code=303)
    if new_password != new_password_repeat:
        return RedirectResponse(url='/cabinet?profile_error=Новые пароли не совпадают', status_code=303)
    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse(url='/cabinet?profile_saved=1', status_code=303)


@router.post('/auth/telegram/update')
def update_telegram_id(
    request: Request,
    telegram_id: str = Form(...),
    db: Session = Depends(get_db),
):
    user_id = request.session.get('user_id')
    if not user_id:
        return _redirect('/login', error='Нужно войти в аккаунт', next='/cabinet')
    user = crud_users.get(db, int(user_id))
    if not user:
        request.session.clear()
        return _redirect('/login', error='Пользователь не найден', next='/cabinet')
    telegram_id = telegram_id.strip()
    if not telegram_id:
        return _redirect('/cabinet', profile_error='Telegram ID не указан')
    exists = db.query(User).filter(User.telegram_id == telegram_id, User.id != user.id).first()
    if exists:
        return _redirect('/cabinet', profile_error='Этот Telegram ID уже привязан к другому аккаунту')
    user.telegram_id = telegram_id
    db.commit()
    return _redirect('/cabinet', telegram_saved='1')


@router.post('/auth/telegram/link-code')
def create_link_code(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get('user_id')
    if not user_id:
        return _redirect('/login', error='Нужно войти в аккаунт', next='/cabinet')
    user = crud_users.get(db, int(user_id))
    if not user:
        request.session.clear()
        return _redirect('/login', error='Пользователь не найден', next='/cabinet')
    code = create_telegram_code(db, user, purpose='link', minutes=20)
    db.commit()
    return _redirect('/cabinet', telegram_code=code.code)


@router.post('/api/telegram/link')
def api_telegram_link(
    code: str = Form(...),
    telegram_id: str = Form(...),
    db: Session = Depends(get_db),
):
    row = consume_telegram_code(db, purpose='link', code=code)
    if not row:
        raise HTTPException(status_code=400, detail='Код недействителен или истек')
    telegram_id = telegram_id.strip()
    if not telegram_id:
        raise HTTPException(status_code=400, detail='telegram_id required')
    exists = db.query(User).filter(User.telegram_id == telegram_id, User.id != row.user_id).first()
    if exists:
        raise HTTPException(status_code=409, detail='Telegram ID уже привязан')
    user = crud_users.get(db, row.user_id)
    if not user:
        raise HTTPException(status_code=404, detail='Пользователь не найден')
    user.telegram_id = telegram_id
    db.commit()
    return {'ok': True, 'user_id': user.id}


@router.post('/auth/telegram/reset/request')
async def telegram_reset_request(
    username: str = Form(...),
    db: Session = Depends(get_db),
):
    user = crud_users.get_by_username(db, username)
    if not user or not user.telegram_id:
        return _redirect('/login', error='У пользователя не привязан Telegram')
    code = create_telegram_code(db, user, purpose='password_reset', telegram_id=user.telegram_id, minutes=15)
    db.commit()
    sent, detail = await send_telegram_message(
        user.telegram_id,
        f"Код восстановления пароля: {code.code}\nОн действует 15 минут.",
    )
    if not sent:
        return _redirect('/password/telegram', username=user.username, error=detail)
    return _redirect('/password/telegram', username=user.username, sent='1')


@router.post('/auth/telegram/reset/confirm')
def telegram_reset_confirm(
    username: str = Form(...),
    code: str = Form(...),
    new_password: str = Form(...),
    new_password_repeat: str = Form(...),
    db: Session = Depends(get_db),
):
    user = crud_users.get_by_username(db, username)
    if not user:
        return _redirect('/password/telegram', username=username, error='Пользователь не найден')
    if len(new_password) < 6:
        return _redirect('/password/telegram', username=username, error='Пароль должен быть от 6 символов')
    if new_password != new_password_repeat:
        return _redirect('/password/telegram', username=username, error='Пароли не совпадают')
    row = consume_telegram_code(db, purpose='password_reset', code=code, user=user, telegram_id=user.telegram_id)
    if not row:
        return _redirect('/password/telegram', username=username, error='Код недействителен или истек')
    user.password_hash = hash_password(new_password)
    db.commit()
    return _redirect('/login', error='Пароль обновлен, войдите с новым паролем')
