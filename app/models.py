from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    telegram_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TelegramAuthCode(Base):
    __tablename__ = "telegram_auth_codes"
    __table_args__ = (
        Index("ix_telegram_auth_codes_user_purpose", "user_id", "purpose"),
        Index("ix_telegram_auth_codes_code_purpose", "code", "purpose"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    telegram_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_user_created", "user_id", "created_at"),
        Index("ix_orders_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    config_id: Mapped[int | None] = mapped_column(ForeignKey("vpn_configs.id"), nullable=True)
    unique_code: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    server_id: Mapped[str] = mapped_column(String(64), index=True)
    period_key: Mapped[str] = mapped_column(String(32))
    amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    action: Mapped[str] = mapped_column(String(32), default="purchase")
    source: Mapped[str] = mapped_column(String(32), default="cabinet")
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    provider_payment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user = relationship("User")
    config = relationship("VpnConfig", foreign_keys=[config_id])


class VpnConfig(Base):
    __tablename__ = "vpn_configs"
    __table_args__ = (
        UniqueConstraint("unique_code", "server_id", name="uq_unique_server"),
        Index("ix_vpn_configs_user_created", "user_id", "created_at"),
        Index("ix_vpn_configs_active_expires", "is_active", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    unique_code: Mapped[str] = mapped_column(String(128), index=True)
    server_id: Mapped[str] = mapped_column(String(64), index=True)
    protocol: Mapped[str] = mapped_column(String(32), default="wireguard", index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    subscription_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_name: Mapped[str] = mapped_column(String(255))
    config_text: Mapped[str] = mapped_column(Text)
    server_host: Mapped[str] = mapped_column(String(255))
    user_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    order = relationship("Order", foreign_keys=[order_id])


class ClaimRecord(Base):
    __tablename__ = "claim_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unique_code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    config_id: Mapped[int | None] = mapped_column(ForeignKey("vpn_configs.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="processed")
    server_id: Mapped[str] = mapped_column(String(64))
    period_key: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaymentLog(Base):
    __tablename__ = "payment_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="platega")
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VpnServer(Base):
    __tablename__ = "vpn_servers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    protocol: Mapped[str] = mapped_column(String(32), default="wg_easy", index=True)
    panel_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    api_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(160), nullable=True)
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    server_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subnet: Mapped[str | None] = mapped_column(String(80), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    max_clients: Mapped[int] = mapped_column(Integer, default=0)
    min_free_ips: Mapped[int] = mapped_column(Integer, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubscriptionPeriod(Base):
    __tablename__ = "subscription_periods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))
    days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[float] = mapped_column(Float, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=100, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProductRoute(Base):
    __tablename__ = "product_routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    item_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    server_ids: Mapped[str] = mapped_column(Text, default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ServerStat(Base):
    __tablename__ = "server_stats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    server_code: Mapped[str] = mapped_column(String(64), index=True)
    protocol: Mapped[str] = mapped_column(String(32), default="wg_easy")
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    total_clients: Mapped[int] = mapped_column(Integer, default=0)
    active_clients: Mapped[int] = mapped_column(Integer, default=0)
    free_ips: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
