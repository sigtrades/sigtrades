import os


class Settings:
    API_SERVER_URL: str = os.getenv("API_SERVER_URL", "http://api-server:8000")
    SIGNAL_ROUTER_URL: str = os.getenv("SIGNAL_ROUTER_URL", "http://signal-router:8000")
    INTERNAL_SECRET: str = os.getenv("INTERNAL_SECRET", "dev-internal-secret")
    DISCORD_PUBLIC_KEY: str = os.getenv("DISCORD_PUBLIC_KEY", "")
    DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_WEBHOOK_SECRET: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    TELEGRAM_WEBHOOK_URL: str = os.getenv("TELEGRAM_WEBHOOK_URL", "")
    TELEGRAM_USE_WEBHOOK: bool = os.getenv("TELEGRAM_USE_WEBHOOK", "false").lower() == "true"
    APP_ENV: str = os.getenv("APP_ENV", "development")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("production", "prod")


settings = Settings()
