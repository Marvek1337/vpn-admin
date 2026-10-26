from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .crud import users as crud_users
from .services.auth import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def _user_from_bearer(credentials: HTTPAuthorizationCredentials | None, db: Session) -> User | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    payload = decode_access_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        return None
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        return None
    return crud_users.get(db, user_id)


def get_current_user_optional(
    request: Request,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User | None:
    bearer_user = _user_from_bearer(credentials, db)
    if bearer_user:
        return bearer_user

    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return crud_users.get(db, int(user_id))


def get_current_user(current_user: User | None = Depends(get_current_user_optional)) -> User:
    if not current_user:
        raise HTTPException(status_code=401, detail="Требуется вход")
    return current_user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Нужен доступ администратора")
    return current_user


def ensure_config_owner(config, current_user: User) -> None:
    if not config or config.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Конфиг не найден")
