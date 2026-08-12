"""relay 通道 WS 协议 schema。

设计要点：
- 反向长连接：Agent 主动连云端 relay-gateway。
- 幂等：execute_signal 带 signal_id / source_id，Agent 本地按 (source_id, signal_id) 去重。
- 回传：Agent 只回传有意义的状态变更（execution_report），含完整成交明细。
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    # ---- 上行：Agent → 云 ----
    AGENT_REGISTER = "agent_register"
    AGENT_HEARTBEAT = "agent_heartbeat"
    AGENT_STATUS = "agent_status"
    EXECUTION_REPORT = "execution_report"
    PROBE_ACCOUNT_RESULT = "probe_account_result"
    # ---- 下行：云 → Agent ----
    EXECUTE_SIGNAL = "execute_signal"
    CANCEL_SIGNAL = "cancel_signal"
    PAUSE_AGENT = "pause_agent"
    PROBE_ACCOUNT = "probe_account"
    ACK = "ack"


# ---------------- 上行消息 ----------------

class AgentRegister(BaseModel):
    """Agent 上线注册：账号 token + 设备绑定 + 能力声明。"""
    type: MessageType = MessageType.AGENT_REGISTER
    user_token: str
    device_id: str
    capabilities: List[str] = Field(default_factory=list)  # 如 ["ibkr", "futu"]
    agent_version: str = "0.1.0"
    platform: str = ""  # darwin / win32


class AgentHeartbeat(BaseModel):
    type: MessageType = MessageType.AGENT_HEARTBEAT
    device_id: str
    ts: float


class AgentStatus(BaseModel):
    """Agent 主动上报网关/券商连通性，供云端展示在线/离线。"""
    type: MessageType = MessageType.AGENT_STATUS
    device_id: str
    brokers: Dict[str, bool] = Field(default_factory=dict)  # {"ibkr": True, "futu": False}
    # 各连接模式状态：[{broker, account_id, name, online, ...}]
    gateways: List[Dict[str, Any]] = Field(default_factory=list)
    detail: Optional[str] = None


class ProbeAccount(BaseModel):
    """云端请求 Agent 探测某本地券商连接/账户。"""
    type: MessageType = MessageType.PROBE_ACCOUNT
    request_id: str
    broker: str
    account_id: Optional[str] = None


class ProbeAccountResult(BaseModel):
    """Agent 回传账户探测结果。"""
    type: MessageType = MessageType.PROBE_ACCOUNT_RESULT
    request_id: str
    ok: bool = False
    broker: str = ""
    account_id: Optional[str] = None
    account_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    device_id: str = ""


class ExecutionReport(BaseModel):
    """执行回执：完整成交明细，云端据此落库（审计/风控/计费）。"""
    type: MessageType = MessageType.EXECUTION_REPORT
    signal_id: str
    source_id: str
    account_id: Optional[str] = None
    broker: str
    order_id: Optional[str] = None
    status: str  # SUBMITTED/FILLED/PARTIALLY_FILLED/CANCELLED/REJECTED/EXPIRED/FAILED/SKIPPED
    symbol: Optional[str] = None
    side: Optional[str] = None  # BUY / SELL
    asset_type: Optional[str] = None  # OPTION / STOCK
    quantity: Optional[float] = None
    limit_price: Optional[float] = None
    fill_price: Optional[float] = None
    filled_qty: Optional[float] = None
    amount: Optional[float] = None  # 成交金额
    realized_pnl: Optional[float] = None  # 已实现盈亏（平仓时有值，供日亏损风控）
    attempt: int = 1
    timestamp: float = 0.0
    error: Optional[str] = None


# ---------------- 下行消息 ----------------

class ExecuteSignal(BaseModel):
    """云端把整条已裁决的信号下发给 Agent（B 模式）。"""
    type: MessageType = MessageType.EXECUTE_SIGNAL
    signal_id: str
    source_id: str
    broker: str  # ibkr / futu
    account_id: Optional[str] = None
    order_type_policy: str = "LMT_then_MKT"  # 或 MKT_only
    signal: Dict[str, Any]  # 序列化后的 Signal（sigtrades_core.signal.models.Signal.to_dict）
    execution_config: Optional[Dict[str, Any]] = None
    risk: Optional[Dict[str, Any]] = None


class CancelSignal(BaseModel):
    type: MessageType = MessageType.CANCEL_SIGNAL
    signal_id: str
    source_id: str
    reason: Optional[str] = None


class PauseAgent(BaseModel):
    """全局急停：停止该 Agent 上的所有自动交易。"""
    type: MessageType = MessageType.PAUSE_AGENT
    paused: bool = True
    reason: Optional[str] = None


class Ack(BaseModel):
    type: MessageType = MessageType.ACK
    ref_type: str
    signal_id: Optional[str] = None
    ok: bool = True
    message: Optional[str] = None


# ---------------- 编解码 ----------------

_MODEL_BY_TYPE = {
    MessageType.AGENT_REGISTER: AgentRegister,
    MessageType.AGENT_HEARTBEAT: AgentHeartbeat,
    MessageType.AGENT_STATUS: AgentStatus,
    MessageType.EXECUTION_REPORT: ExecutionReport,
    MessageType.PROBE_ACCOUNT_RESULT: ProbeAccountResult,
    MessageType.EXECUTE_SIGNAL: ExecuteSignal,
    MessageType.CANCEL_SIGNAL: CancelSignal,
    MessageType.PAUSE_AGENT: PauseAgent,
    MessageType.PROBE_ACCOUNT: ProbeAccount,
    MessageType.ACK: Ack,
}


def encode_message(msg: BaseModel) -> str:
    """序列化为 JSON 字符串（用于 WS 发送）。"""
    return msg.model_dump_json()


def decode_message(raw: str | bytes | Dict[str, Any]) -> BaseModel:
    """从原始 WS 文本/字典解析为对应的 pydantic 模型。"""
    data: Dict[str, Any] = raw if isinstance(raw, dict) else json.loads(raw)
    mtype = MessageType(data.get("type"))
    model = _MODEL_BY_TYPE.get(mtype)
    if model is None:
        raise ValueError(f"未知消息类型: {mtype}")
    return model.model_validate(data)
