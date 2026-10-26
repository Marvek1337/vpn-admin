from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 7005
    session_secret: str = "change-me"
    jwt_secret: str = "change-me-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60 * 24 * 7
    public_base_url: str = "http://127.0.0.1:7005"
    database_url: str = "sqlite:///./data/app.db"
    admin_username: str = "admin"
    admin_password: str = "change-me"
    expired_config_grace_days: int = 1
    bot_payment_callback_url: str = ""
    allow_test_payments: bool = False

    ggsel_base_url: str = "https://seller.ggsel.com/api_sellers/api"
    ggsel_seller_id: str = ""
    ggsel_api_key: str = ""
    ggsel_product_update_endpoint: str = ""
    ggsel_product_update_payload: dict[str, str] = {
        "product_id": "{product_id}",
        "active": "{active}",
    }

    platega_enabled: bool = False
    platega_base_url: str = "https://app.platega.io"
    platega_merchant_id: str = ""
    platega_secret: str = ""
    platega_payment_method: int = 2
    platega_currency: str = "RUB"
    platega_callback_secret: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
