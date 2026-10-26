from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
from passlib.hash import pbkdf2_sha256
from ..settings import settings


def hash_password(password: str) -> str:
    return pbkdf2_sha256.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pbkdf2_sha256.verify(password, password_hash)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(message: str) -> str:
    digest = hmac.new(settings.jwt_secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256).digest()
    return _b64url(digest)


def create_access_token(user_id: int, is_admin: bool = False) -> str:
    now = datetime.now(timezone.utc)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "is_admin": bool(is_admin),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_token_minutes)).timestamp()),
    }
    signing_input = ".".join([
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ])
    return f"{signing_input}.{_sign(signing_input)}"


def decode_access_token(token: str) -> dict | None:
    try:
        header_b64, payload_b64, signature = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}"
        if not hmac.compare_digest(_sign(signing_input), signature):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return payload
    except Exception:
        return None
