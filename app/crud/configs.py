from sqlalchemy.orm import Session

from ..models import VpnConfig


def get(db: Session, config_id: int) -> VpnConfig | None:
    return db.get(VpnConfig, config_id)


def get_for_user(db: Session, config_id: int, user_id: int) -> VpnConfig | None:
    return db.query(VpnConfig).filter(
        VpnConfig.id == config_id, VpnConfig.user_id == user_id,
    ).first()


def get_by_unique_server(db: Session, unique_code: str, server_id: str) -> VpnConfig | None:
    return db.query(VpnConfig).filter(
        VpnConfig.unique_code == unique_code, VpnConfig.server_id == server_id,
    ).first()


def list_for_user(db: Session, user_id: int) -> list[VpnConfig]:
    return db.query(VpnConfig).filter(VpnConfig.user_id == user_id).order_by(VpnConfig.id.desc()).all()
