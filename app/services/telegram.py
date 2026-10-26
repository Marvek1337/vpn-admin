from __future__ import annotations

from datetime import datetime, timedelta
import secrets
import string

import httpx
from sqlalchemy.orm import Session

from app.config import get_runtime_config
from app.models import TelegramAuthCode, User


CODE_ALPHABET = string.ascii_uppercase + string.digits


def _new_code(length: int = 8) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def create_telegram_code(
    db: Session,
    user: User,
    purpose: str,
    telegram_id: str | None = None,
    minutes: int = 15,
) -> TelegramAuthCode:
    now = datetime.utcnow()
    db.query(TelegramAuthCode).filter(
        TelegramAuthCode.user_id == user.id,
        TelegramAuthCode.purpose == purpose,
        TelegramAuthCode.used_at.is_(None),
    ).update({"used_at": now})
    code = TelegramAuthCode(
        user_id=user.id,
        telegram_id=(telegram_id or user.telegram_id or None),
        purpose=purpose,
        code=_new_code(),
        expires_at=now + timedelta(minutes=minutes),
        created_at=now,
    )
    db.add(code)
    db.flush()
    return code


def consume_telegram_code(
    db: Session,
    purpose: str,
    code: str,
    user: User | None = None,
    telegram_id: str | None = None,
) -> TelegramAuthCode | None:
    normalized = code.strip().upper()
    query = db.query(TelegramAuthCode).filter(
        TelegramAuthCode.purpose == purpose,
        TelegramAuthCode.code == normalized,
        TelegramAuthCode.used_at.is_(None),
        TelegramAuthCode.expires_at >= datetime.utcnow(),
    )
    if user:
        query = query.filter(TelegramAuthCode.user_id == user.id)
    if telegram_id:
        query = query.filter(TelegramAuthCode.telegram_id == telegram_id.strip())
    row = query.order_by(TelegramAuthCode.id.desc()).first()
    if not row:
        return None
    row.used_at = datetime.utcnow()
    return row


async def send_telegram_message(telegram_id: str, text: str) -> tuple[bool, str]:
    runtime = get_runtime_config()
    token = (runtime.get("telegram", {}) or {}).get("bot_token") or ""
    if not token:
        return False, "Telegram bot token не настроен"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(url, json={"chat_id": telegram_id, "text": text})
        if response.status_code >= 400:
            return False, response.text[:500]
        payload = response.json()
        if not payload.get("ok"):
            return False, str(payload)[:500]
        return True, "sent"
    except Exception as exc:
        return False, str(exc)[:500]
