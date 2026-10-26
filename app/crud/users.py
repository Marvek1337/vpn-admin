from sqlalchemy.orm import Session
from ..models import User


def get(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username.strip()).first()


def create(db: Session, username: str, password_hash: str, telegram_id: str | None = None, is_admin: bool = False) -> User:
    user = User(username=username.strip(), password_hash=password_hash, telegram_id=telegram_id or None, is_admin=is_admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
