import os


class Settings:
    """cloud-executor 配置。"""

    API_SERVER_URL: str = os.getenv("API_SERVER_URL", "http://api-server:8000")
    INTERNAL_SECRET: str = os.getenv("INTERNAL_SECRET", "dev-internal-secret")
    REPORT_SINK_URL: str = os.getenv(
        "REPORT_SINK_URL", "http://api-server:8000/internal/execution-report"
    )
    # Fernet 密钥（应用层加密老虎私钥）。生产从密钥管理注入。
    FERNET_KEY: str = os.getenv("FERNET_KEY", "")
    # 并发执行线程数
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "8"))
    # 单次云端执行最长等待（秒）；超时后写 EXPIRED 回执
    EXECUTE_TIMEOUT_SEC: int = int(os.getenv("EXECUTE_TIMEOUT_SEC", "120"))


settings = Settings()
