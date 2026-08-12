"""信号源统一标准接口。

类比 `BaseBrokerAdapter`：每个外部平台实现一个 source/connector，把异构 payload
归一化为 sigtrades 内部 `Signal`。外部源的专有协议/字段封闭在各自实现内，下游对来源无感知。

新增外部源 = 实现一个 BaseSignalSource + 注册配置，不改动下游任何代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from sigtrades_core.signal.models import Signal


class Ownership(str, Enum):
    """信号源归属类型。"""
    PLATFORM_SHARED = "platform_shared"   # 一条信号广播给多个订阅者
    USER_PRIVATE = "user_private"         # 一条信号只属于源所属用户


@dataclass
class NormalizedSignal:
    """归一化结果：内部信号 + 来源元信息。"""
    signal: Signal
    source_id: str
    ownership: Ownership
    owner_user_id: Optional[str] = None    # USER_PRIVATE 时必填
    raw: Optional[Dict[str, Any]] = None   # 原始 payload（审计/排障）
    confidence: float = 1.0                # 解析置信度（AI 解析用）


# 归一化信号产出回调：source 解析出信号后调用，交给上游（ingest/router）
EmitCallback = Callable[[NormalizedSignal], None]


class BaseSignalSource(ABC):
    """信号源（connector）抽象基类。"""

    #: 平台标识，如 "discord" / "tradingview" / "telegram" / "ws"
    kind: str = "generic"

    def __init__(self, source_id: str, config: Dict[str, Any], on_signal: EmitCallback):
        self.source_id = source_id
        self.config = config
        self.on_signal = on_signal

    @property
    @abstractmethod
    def ownership(self) -> Ownership:
        """该源的归属类型。"""

    @abstractmethod
    def start(self) -> None:
        """启动监听/订阅（WS 连接、bot gateway、webhook 注册等）。"""

    @abstractmethod
    def stop(self) -> None:
        """停止并释放资源。"""

    @abstractmethod
    def parse(self, raw: Any) -> List[NormalizedSignal]:
        """把一条原始 payload 解析为零或多条归一化信号。"""

    # 便捷：解析并 emit
    def ingest_raw(self, raw: Any) -> None:
        for ns in self.parse(raw):
            self.on_signal(ns)
