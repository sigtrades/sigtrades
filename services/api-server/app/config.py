import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://sigtrades:sigtrades@localhost:5432/sigtrades",
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    INTERNAL_SECRET: str = os.getenv("INTERNAL_SECRET", "dev-internal-secret")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-jwt-secret-change-in-prod")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_MINUTES: int = int(os.getenv("JWT_ACCESS_MINUTES", "60"))
    JWT_REFRESH_DAYS: int = int(os.getenv("JWT_REFRESH_DAYS", "30"))
    FERNET_KEY: str = os.getenv("FERNET_KEY", "")
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    # 关闭后禁止新建 Stripe Checkout（兑换码 / 管理员发 Pro 不受影响）
    BILLING_CHECKOUT_ENABLED: bool = os.getenv("BILLING_CHECKOUT_ENABLED", "false").lower() == "true"
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    # OpenAI-compat AI（与 sunny-quant 一致；解析优先 AI_API_KEY）
    AI_CLIENT_MODE: str = os.getenv("AI_CLIENT_MODE", "openai")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")
    AI_OPENAI_COMPAT_BASE: str = os.getenv("AI_OPENAI_COMPAT_BASE", "https://www.packyapi.com")
    # packyapi：gpt-5.5 不支持 chat completions，解析默认用 gpt-5.4
    AI_MODEL: str = os.getenv("AI_MODEL", "gpt-5.4")
    AI_MAX_TOKENS: int = int(os.getenv("AI_MAX_TOKENS", "2000") or "2000")
    AI_TIMEOUT: float = float(os.getenv("AI_TIMEOUT", os.getenv("AI_TRANSLATE_TIMEOUT", "30")) or "30")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
    RELAY_AGENT_WS_URL: str = os.getenv(
        "RELAY_AGENT_WS_URL",
        "wss://agent.sigtrades.com/agent/ws",
    )
    RELAY_GATEWAY_URL: str = os.getenv("RELAY_GATEWAY_URL", "http://relay-gateway:8000")
    CLOUD_EXECUTOR_URL: str = os.getenv("CLOUD_EXECUTOR_URL", "http://cloud-executor:8000")
    INGEST_URL: str = os.getenv("INGEST_URL", "http://ingest:8000")
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    REQUIRE_EMAIL_VERIFICATION: bool = os.getenv("REQUIRE_EMAIL_VERIFICATION", "false").lower() == "true"
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@sigtrades.app")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL", "")
    RESEND_FROM_NAME: str = os.getenv("RESEND_FROM_NAME", "sigtrades")
    RESEND_WEBHOOK_SECRET: str = os.getenv("RESEND_WEBHOOK_SECRET", "")
    GEOIP2_CITY_DB_PATH: str = os.getenv("GEOIP2_CITY_DB_PATH", "data/geoip/GeoLite2-City.mmdb")
    GEOIP2_COUNTRY_DB_PATH: str = os.getenv("GEOIP2_COUNTRY_DB_PATH", "data/geoip/GeoLite2-Country.mmdb")
    DISCORD_APPLICATION_ID: str = os.getenv("DISCORD_APPLICATION_ID", "")
    DISCORD_BOT_PERMISSIONS: str = os.getenv("DISCORD_BOT_PERMISSIONS", "68608")
    NOTIFY_PUSH_WEBHOOK: str = os.getenv("NOTIFY_PUSH_WEBHOOK", "")
    # FCM HTTP v1（推荐；替代已停用的 Legacy server key）
    FCM_PROJECT_ID: str = os.getenv("FCM_PROJECT_ID", "")
    FCM_CREDENTIALS_JSON: str = os.getenv("FCM_CREDENTIALS_JSON", "")
    FCM_CREDENTIALS_PATH: str = os.getenv("FCM_CREDENTIALS_PATH", "")
    ALLOW_INSECURE_INBOUND_WEBHOOK: bool = os.getenv("ALLOW_INSECURE_INBOUND_WEBHOOK", "false").lower() == "true"
    # Agent 版本 / Firebase Web（公开配置）
    AGENT_LATEST_VERSION: str = os.getenv("AGENT_LATEST_VERSION", "0.1.0")
    AGENT_DOWNLOAD_URL: str = os.getenv("AGENT_DOWNLOAD_URL", "")
    AGENT_SHA256: str = os.getenv("AGENT_SHA256", "")
    AGENT_WINDOWS_LATEST_VERSION: str = os.getenv("AGENT_WINDOWS_LATEST_VERSION", "")
    AGENT_WINDOWS_DOWNLOAD_URL: str = os.getenv("AGENT_WINDOWS_DOWNLOAD_URL", "")
    AGENT_WINDOWS_SHA256: str = os.getenv("AGENT_WINDOWS_SHA256", "")
    AGENT_RELEASES_DIR: str = os.getenv("AGENT_RELEASES_DIR", "/app/data/agent-releases")
    # 后台「加载本地包」拼下载 URL 用；默认与本地 Docker 一致
    AGENT_RELEASES_PUBLIC_BASE: str = os.getenv(
        "AGENT_RELEASES_PUBLIC_BASE",
        "http://localhost:8080/releases",
    )
    FIREBASE_WEB_API_KEY: str = os.getenv("FIREBASE_WEB_API_KEY", "")
    FIREBASE_MESSAGING_SENDER_ID: str = os.getenv("FIREBASE_MESSAGING_SENDER_ID", "")
    FIREBASE_WEB_APP_ID: str = os.getenv("FIREBASE_WEB_APP_ID", "")
    FIREBASE_VAPID_KEY: str = os.getenv("FIREBASE_VAPID_KEY", "")
    FIREBASE_AUTH_DOMAIN: str = os.getenv("FIREBASE_AUTH_DOMAIN", "")
    DISCORD_OAUTH_REDIRECT_URI: str = os.getenv(
        "DISCORD_OAUTH_REDIRECT_URI",
        "http://localhost:8080/config/discord/callback",
    )
    # 须与 Schwab Developer Portal 的 Callback URL 完全一致（推荐 https://127.0.0.1）
    SCHWAB_OAUTH_REDIRECT_URI: str = os.getenv(
        "SCHWAB_OAUTH_REDIRECT_URI",
        "https://127.0.0.1",
    )
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    SEED_DEMO: bool = os.getenv("SEED_DEMO", "true").lower() == "true"
    # production / development。生产环境会强制校验关键密钥（拒绝默认值/空值）。
    APP_ENV: str = os.getenv("APP_ENV", "development")
    # 幂等在飞窗口（秒）：ROUTING/DISPATCHED 在此窗口内视为重复。
    IDEM_IN_FLIGHT_SEC: int = int(os.getenv("IDEM_IN_FLIGHT_SEC", "300"))

    # Admin / operations backend
    ADMIN_TOKEN: str = os.getenv("ADMIN_TOKEN", "dev-admin-token-change-me")
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    OPERATIONS_USERNAME: str = os.getenv("OPERATIONS_USERNAME", "ops")
    OPERATIONS_PASSWORD: str = os.getenv("OPERATIONS_PASSWORD", "ops123")
    OPERATIONS_TOKEN: str = os.getenv("OPERATIONS_TOKEN", "operations-token-change-me")

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("production", "prod")

    def effective_ai_api_key(self) -> str:
        return (self.AI_API_KEY or self.OPENAI_API_KEY or "").strip()

    def openai_compat_base_url(self) -> str:
        root = (self.AI_OPENAI_COMPAT_BASE or "https://www.packyapi.com").strip().rstrip("/")
        if not root:
            return "https://api.openai.com/v1"
        return root if root.endswith("/v1") else f"{root}/v1"

    def ai_parse_kwargs(self) -> dict:
        """传给 parse_ai / apply_parse_rules 的 AI 参数。"""
        return {
            "openai_api_key": self.effective_ai_api_key() or None,
            "openai_base_url": self.openai_compat_base_url(),
            "openai_model": (self.AI_MODEL or "gpt-5.4").strip() or "gpt-5.4",
            "openai_max_tokens": max(256, min(int(self.AI_MAX_TOKENS or 2000), 20000)),
            "openai_timeout": float(self.AI_TIMEOUT or 30),
        }


_INSECURE_DEFAULTS = {
    "INTERNAL_SECRET": "dev-internal-secret",
    "JWT_SECRET": "dev-jwt-secret-change-in-prod",
}


def validate_production_secrets(s: "Settings") -> None:
    """生产环境启动前校验：默认/空的关键密钥直接拒绝启动（fail-fast）。"""
    if not s.is_production:
        return
    problems: list[str] = []
    for name, insecure in _INSECURE_DEFAULTS.items():
        val = getattr(s, name, "")
        if not val or val == insecure:
            problems.append(f"{name} 仍为默认/空值")
    if not s.FERNET_KEY:
        problems.append("FERNET_KEY 未配置（券商凭证加密必需）")
    if s.STRIPE_SECRET_KEY and not s.STRIPE_WEBHOOK_SECRET:
        problems.append("启用 Stripe 但 STRIPE_WEBHOOK_SECRET 未配置（webhook 无法验签）")
    admin_token = settings.ADMIN_TOKEN
    if not admin_token or admin_token == "dev-admin-token-change-me":
        problems.append("ADMIN_TOKEN 仍为默认/空值")
    if problems:
        raise RuntimeError(
            "生产环境配置不安全，拒绝启动：\n- " + "\n- ".join(problems)
        )


settings = Settings()
