"""Agent 连接认证：校验 user_token 并解析出 user_id。

向 api-server 内部端点校验。dev 模式下可信任 token（token 即 user_id）。
"""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def authenticate_agent(user_token: str, device_id: str) -> Optional[str]:
    """返回 user_id，失败返回 None。"""
    if not user_token or not device_id:
        return None

    if settings.DEV_TRUST_TOKEN:
        # dev: token 直接作为 user_id
        return user_token

    url = f"{settings.API_SERVER_URL}/internal/claim-agent-ws"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            resp = await client.post(
                url,
                json={"user_token": user_token, "device_id": device_id},
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
        if resp.status_code == 200:
            return resp.json().get("user_id")
        logger.warning("token 校验失败: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:  # noqa: BLE001
        logger.error("调用 api-server 校验 token 异常: %s", e)
    return None
