from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    is_admin: bool


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    config_id: int | None
    unique_code: str | None
    server_id: str
    period_key: str
    amount: float
    status: str
    action: str
    source: str
    provider: str | None
    payment_method: str | None
    provider_payment_id: str | None
    provider_payment_url: str | None
    provider_status: str | None
    error_message: str | None
    applied_at: datetime | None
    created_at: datetime
    paid_at: datetime | None


class ConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    order_id: int | None
    unique_code: str
    server_id: str
    config_name: str
    protocol: str
    server_host: str
    user_note: str | None
    expires_at: datetime | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
