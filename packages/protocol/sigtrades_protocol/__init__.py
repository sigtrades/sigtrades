"""sigtrades_protocol: 云端 ↔ Agent 的 relay WS 协议与内部契约。

所有 relay 消息都是 JSON，含顶层 `type` 字段。上行=Agent→云，下行=云→Agent。
"""

from sigtrades_protocol.relay import (
    MessageType,
    AgentRegister,
    AgentHeartbeat,
    AgentStatus,
    ExecutionReport,
    ExecuteSignal,
    CancelSignal,
    Ack,
    PauseAgent,
    ProbeAccount,
    ProbeAccountResult,
    decode_message,
    encode_message,
)

__all__ = [
    "MessageType",
    "AgentRegister",
    "AgentHeartbeat",
    "AgentStatus",
    "ExecutionReport",
    "ExecuteSignal",
    "CancelSignal",
    "Ack",
    "PauseAgent",
    "ProbeAccount",
    "ProbeAccountResult",
    "decode_message",
    "encode_message",
]

__version__ = "0.1.0"
