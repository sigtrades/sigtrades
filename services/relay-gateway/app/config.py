import os


class Settings:
    """relay-gateway 配置（环境变量驱动）。"""

    # api-server 内部地址，用于校验 user_token
    API_SERVER_URL: str = os.getenv("API_SERVER_URL", "http://api-server:8000")
    # 内部服务间共享密钥（cloud-core/signal-router 调用 dispatch 时校验）
    INTERNAL_SECRET: str = os.getenv("INTERNAL_SECRET", "dev-internal-secret")
    # 上报执行回执转发到 api-server 的内部端点
    REPORT_SINK_URL: str = os.getenv(
        "REPORT_SINK_URL", "http://api-server:8000/internal/execution-report"
    )
    HEARTBEAT_TIMEOUT: float = float(os.getenv("HEARTBEAT_TIMEOUT", "60"))
    # 本地开发时跳过 api-server token 校验（仅 dev）
    DEV_TRUST_TOKEN: bool = os.getenv("DEV_TRUST_TOKEN", "false").lower() == "true"


settings = Settings()
