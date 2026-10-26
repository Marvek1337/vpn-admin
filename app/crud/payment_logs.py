import json

from sqlalchemy.orm import Session

from ..models import PaymentLog


def create(db: Session, *, order_id: int | None, provider: str,
           provider_payment_id: str | None, status: str | None, payload: dict) -> PaymentLog:
    row = PaymentLog(
        order_id=order_id, provider=provider, provider_payment_id=provider_payment_id,
        status=status, payload=json.dumps(payload, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
