"""Agent 连接管理：user_id → device_id → WebSocket，路由 + 离线判定。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class AgentConnection:
    user_id: str
    device_id: str
    ws: WebSocket
    capabilities: List[str] = field(default_factory=list)
    platform: str = ""
    agent_version: str = ""
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    brokers: Dict[str, bool] = field(default_factory=dict)
    gateways: List[dict] = field(default_factory=list)
    paused: bool = False

    def supports(self, broker: str) -> bool:
        return broker in self.capabilities


class ConnectionManager:
    def __init__(self):
        # user_id -> {device_id -> AgentConnection}
        self._conns: Dict[str, Dict[str, AgentConnection]] = {}

    async def register(self, conn: AgentConnection) -> list[AgentConnection]:
        """登记连接；踢掉同账号下其它设备，以及同 device 的旧 socket。

        同 device 重连时必须把旧连接列入 displaced：否则旧 WS 的 finally
        里 ``remove(device_id)`` 会误删新登记，presence 变成「登录后离线」。
        """
        user_devices = self._conns.setdefault(conn.user_id, {})
        displaced: List[AgentConnection] = []
        old_same = user_devices.get(conn.device_id)
        if old_same is not None and old_same is not conn:
            displaced.append(old_same)
        displaced.extend(
            c for did, c in list(user_devices.items()) if did != conn.device_id
        )
        user_devices[conn.device_id] = conn
        logger.info("Agent 上线 user=%s device=%s caps=%s", conn.user_id, conn.device_id, conn.capabilities)
        return displaced

    def remove(
        self,
        user_id: str,
        device_id: str,
        *,
        conn: Optional[AgentConnection] = None,
    ) -> None:
        """移除连接。传入 ``conn`` 时仅当仍是当前登记对象才删除（防旧 socket 误删新连接）。"""
        devices = self._conns.get(user_id)
        if not devices or device_id not in devices:
            return
        current = devices[device_id]
        if conn is not None and current is not conn:
            logger.info(
                "忽略过期下线 user=%s device=%s（已有更新连接）",
                user_id,
                device_id,
            )
            return
        del devices[device_id]
        if not devices:
            self._conns.pop(user_id, None)
        logger.info("Agent 离线 user=%s device=%s", user_id, device_id)

    def get_device(self, user_id: str, device_id: str) -> Optional[AgentConnection]:
        return self._conns.get(user_id, {}).get(device_id)

    def list_user(self, user_id: str) -> List[AgentConnection]:
        return list(self._conns.get(user_id, {}).values())

    def find_for_broker(self, user_id: str, broker: str, device_id: Optional[str] = None) -> Optional[AgentConnection]:
        """为指定用户+券商挑选一个在线且未暂停的 Agent。"""
        candidates = self.list_user(user_id)
        if device_id:
            candidates = [c for c in candidates if c.device_id == device_id]
        for c in candidates:
            if not c.paused and c.supports(broker) and c.brokers.get(broker, True):
                return c
        # 退化：支持该券商但 broker 连通性未知
        for c in candidates:
            if not c.paused and c.supports(broker):
                return c
        return None

    def online_brokers(self, user_id: str) -> Dict[str, bool]:
        """汇总该用户所有在线 Agent 提供的券商连通性。"""
        result: Dict[str, bool] = {}
        for c in self.list_user(user_id):
            for b in c.capabilities:
                result[b] = result.get(b, False) or c.brokers.get(b, False)
        return result

    def touch(self, user_id: str, device_id: str) -> None:
        conn = self.get_device(user_id, device_id)
        if conn:
            conn.last_heartbeat = time.time()

    def disconnect_user(self, user_id: str) -> list[AgentConnection]:
        devices = self._conns.pop(user_id, {})
        conns = list(devices.values())
        for conn in conns:
            logger.info("Agent 被挤下线 user=%s device=%s", user_id, conn.device_id)
        return conns


manager = ConnectionManager()
