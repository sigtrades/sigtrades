import os


class Settings:
    """signal-router 配置。"""

    API_SERVER_URL: str = os.getenv("API_SERVER_URL", "http://api-server:8000")
    RELAY_GATEWAY_URL: str = os.getenv("RELAY_GATEWAY_URL", "http://relay-gateway:8000")
    CLOUD_EXECUTOR_URL: str = os.getenv("CLOUD_EXECUTOR_URL", "http://cloud-executor:8000")
    NOTIFY_URL: str = os.getenv("NOTIFY_URL", "http://api-server:8000/internal/notify")
    INTERNAL_SECRET: str = os.getenv("INTERNAL_SECRET", "dev-internal-secret")
    # dev：路由计划允许直接由入站 envelope 携带，不强制查 api-server
    DEV_ALLOW_EMBEDDED_PLAN: bool = os.getenv("DEV_ALLOW_EMBEDDED_PLAN", "true").lower() == "true"


settings = Settings()
