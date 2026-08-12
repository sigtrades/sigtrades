"""通过浏览器完成 Agent 登录，无需手动复制 Token。"""

from __future__ import annotations

import logging
import os
import time
import webbrowser

import httpx

from sigtrades_agent.cloud_defaults import DEFAULT_API_URL, DEFAULT_WEB_URL
from sigtrades_agent.config import AgentConfig, save_config

logger = logging.getLogger("browser-login")

LOGIN_TIMEOUT_SECONDS = 300.0
POLL_INTERVAL_SECONDS = 1.5


def _api_base() -> str:
    return os.getenv("SIGTRADES_API_URL", DEFAULT_API_URL).rstrip("/")


def _web_base() -> str:
    return os.getenv("SIGTRADES_WEB_URL", DEFAULT_WEB_URL).rstrip("/")


def login_via_browser(cfg: AgentConfig) -> AgentConfig:
    """打开现有 Web 前端授权，并轮询云端领取一次性 token。"""
    logger.info("启动浏览器登录 flow (device=%s)", cfg.device_id)
    with httpx.Client(timeout=15.0, trust_env=False) as client:
        resp = client.post(
            f"{_api_base()}/public/agent-connect/session",
            json={"device_id": cfg.device_id},
        )
        resp.raise_for_status()
        data = resp.json()

        connect_url = data.get("connect_url") or ""
        if not connect_url:
            connect_url = f"{_web_base()}/agent/connect?state={data['state']}"
        logger.info("打开浏览器: %s", connect_url)
        webbrowser.open(connect_url)

        deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
        result: dict = {}
        while time.monotonic() < deadline:
            poll = client.post(
                f"{_api_base()}/public/agent-connect/poll",
                json={
                    "session_id": data["session_id"],
                    "poll_secret": data["poll_secret"],
                },
            )
            poll.raise_for_status()
            result = poll.json()
            if result.get("status") == "authorized":
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        else:
            raise TimeoutError("browser login timed out")

    token = str(result.get("token") or "")
    if not token:
        raise RuntimeError("browser login response missing token")
    cfg.user_token = token
    relay_url = str(result.get("relay_url") or "").strip()
    if relay_url:
        cfg.relay_url = relay_url
    email = str(result.get("email") or "").strip()
    if email:
        cfg.account_email = email
    save_config(cfg)
    logger.info("浏览器登录成功，token 已保存")
    return cfg
