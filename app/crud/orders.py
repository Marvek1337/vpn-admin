from sqlalchemy.orm import Session

from ..models import Order


def create(db: Session, **values) -> Order:
    order = Order(**values)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_for_user(db: Session, order_id: int, user_id: int) -> Order | None:
    return db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()


def get_by_payment_id(db: Session, payment_id: str) -> Order | None:
    return db.query(Order).filter(Order.provider_payment_id == payment_id).first()


def list_for_user(db: Session, user_id: int) -> list[Order]:
    return db.query(Order).filter(Order.user_id == user_id).order_by(Order.id.desc()).all()
