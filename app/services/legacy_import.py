from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3

from sqlalchemy.orm import Session

from app.models import User, VpnConfig, VpnServer


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {str(row[0]) for row in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _get(row: sqlite3.Row, key: str, default=None):
    return row[key] if key in row.keys() else default


def _parse_dt(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        try:
            return datetime.utcfromtimestamp(int(text))
        except Exception:
            return None
    for candidate in (text, text.replace("Z", "+00:00"), text[:19]):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=None)
        except Exception:
            continue
    return None


def _parse_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on", "да", "active"}


def import_legacy_sqlite(
    db: Session,
    source_path: str,
    import_users: bool = True,
    overwrite_configs: bool = False,
) -> dict:
    path = Path(source_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")

    result = {
        "source": str(path),
        "users_created": 0,
        "users_updated": 0,
        "configs_created": 0,
        "configs_updated": 0,
        "configs_skipped": 0,
        "missing_servers": [],
    }
    user_map: dict[int, int] = {}

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        tables = _tables(conn)
        if "users" in tables and import_users:
            for row in conn.execute("SELECT * FROM users"):
                old_id = _get(row, "id")
                username = str(_get(row, "username", "") or "").strip()
                password_hash = str(_get(row, "password_hash", "") or "").strip()
                if not username or not password_hash:
                    continue
                existing = db.query(User).filter(User.username == username).first()
                if existing:
                    if _get(row, "telegram_id") and not existing.telegram_id:
                        existing.telegram_id = str(_get(row, "telegram_id"))
                        result["users_updated"] += 1
                    user_map[int(old_id)] = existing.id
                    continue
                user = User(
                    username=username,
                    password_hash=password_hash,
                    telegram_id=str(_get(row, "telegram_id")) if _get(row, "telegram_id") else None,
                    is_admin=_parse_bool(_get(row, "is_admin"), False),
                    created_at=_parse_dt(_get(row, "created_at")) or datetime.utcnow(),
                )
                db.add(user)
                db.flush()
                if old_id is not None:
                    user_map[int(old_id)] = user.id
                result["users_created"] += 1

        if "vpn_configs" not in tables:
            raise RuntimeError("В старой базе нет таблицы vpn_configs")

        cols = _columns(conn, "vpn_configs")
        known_servers = {row.code for row in db.query(VpnServer.code).all()}
        for row in conn.execute("SELECT * FROM vpn_configs"):
            unique_code = str(_get(row, "unique_code", "") or "").strip()
            server_id = str(_get(row, "server_id", "") or "").strip()
            if not unique_code or not server_id:
                result["configs_skipped"] += 1
                continue
            if known_servers and server_id not in known_servers and server_id not in result["missing_servers"]:
                result["missing_servers"].append(server_id)

            existing = db.query(VpnConfig).filter(
                VpnConfig.unique_code == unique_code,
                VpnConfig.server_id == server_id,
            ).first()
            if existing and not overwrite_configs:
                result["configs_skipped"] += 1
                continue

            old_user_id = _get(row, "user_id")
            mapped_user_id = user_map.get(int(old_user_id)) if old_user_id is not None else None
            payload = {
                "user_id": mapped_user_id,
                "order_id": None,
                "unique_code": unique_code,
                "server_id": server_id,
                "protocol": str(_get(row, "protocol", "wireguard") or "wireguard"),
                "external_id": _get(row, "external_id") if "external_id" in cols else None,
                "subscription_url": _get(row, "subscription_url") if "subscription_url" in cols else None,
                "config_name": str(_get(row, "config_name", unique_code) or unique_code),
                "config_text": str(_get(row, "config_text", "") or ""),
                "server_host": str(_get(row, "server_host", server_id) or server_id),
                "user_note": _get(row, "user_note") if "user_note" in cols else None,
                "expires_at": _parse_dt(_get(row, "expires_at")),
                "is_active": _parse_bool(_get(row, "is_active"), True),
                "created_at": _parse_dt(_get(row, "created_at")) or datetime.utcnow(),
                "updated_at": _parse_dt(_get(row, "updated_at")) or datetime.utcnow(),
            }
            if existing:
                for key, value in payload.items():
                    if key in {"unique_code", "server_id"}:
                        continue
                    setattr(existing, key, value)
                result["configs_updated"] += 1
            else:
                db.add(VpnConfig(**payload))
                result["configs_created"] += 1
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        conn.close()
