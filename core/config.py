import os

from dotenv import load_dotenv

load_dotenv()


def _db_url(raw: str) -> str:
    """Render отдаёт postgres://, SQLAlchemy async требует postgresql+asyncpg://"""
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    return raw


class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    database_url: str = _db_url(os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./local.db"))
    redis_url: str = os.getenv("REDIS_URL", "")

    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_stt_model: str = os.getenv("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")
    secret_key: str = os.getenv("SECRET_KEY", "")  # Fernet-ключ для шифрования логинов поставщиков

    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

    # Webhook (Render). Если BASE_URL пуст — бот работает через polling (локальная разработка)
    base_url: str = os.getenv("BASE_URL", "").rstrip("/")
    webhook_secret: str = os.getenv("WEBHOOK_SECRET", "change-me")
    port: int = int(os.getenv("PORT", "8080"))

    demo_mode: bool = os.getenv("DEMO_MODE", "") in ("1", "true", "True")

    # Отправка заказов менеджерам
    green_api_instance: str = os.getenv("GREEN_API_INSTANCE", "")
    green_api_token: str = os.getenv("GREEN_API_TOKEN", "")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")

    # Монетизация
    trial_days: int = int(os.getenv("TRIAL_DAYS", "14"))
    subscription_days: int = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
    subscription_price_stars: int = int(os.getenv("SUBSCRIPTION_PRICE_STARS", "500"))


settings = Settings()
