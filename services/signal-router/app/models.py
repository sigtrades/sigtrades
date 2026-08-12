"""signal-router 入站/路由领域模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    AUTO_TRADE = "auto_trade"
    NOTIFY_ONLY = "notify_only"
    CONFIRM_TRADE = "confirm_trade"
    BOTH = "both"


class BrokerBinding(BaseModel):
    """某用户在某券商的绑定（一个下单目标）。"""
    broker: str                      # tiger / ibkr / futu
    account_id: Optional[str] = None
    account_label: Optional[str] = None
    device_id: Optional[str] = None  # gateway 券商：指定 Agent 设备
    order_type_policy: str = "LMT_then_MKT"


class UserRoutePlan(BaseModel):
    """单用户对该信号的路由决策（由 api-server 解析或 dev envelope 携带）。"""
    user_id: str
    action: ActionType = ActionType.AUTO_TRADE
    bindings: List[BrokerBinding] = Field(default_factory=list)
    risk: Optional[Dict[str, Any]] = None
    execution_config: Optional[Dict[str, Any]] = None
    language: str = "zh"
    risk_blocked: Optional[str] = None
    entitlement_blocked: Optional[str] = None  # kill_switch / plan_no_auto_trade
    routing_blocked: Optional[str] = None  # ambiguous_broker_account 等
    target_broker: Optional[str] = None  # 规则指定券商；拦截落库用，避免 broker="-" 被流水线滤掉


class InboundSignal(BaseModel):
    """ingest / 外部信号服务 投递给 signal-router 的归一化信号信封。"""
    source_id: str
    signal_id: str
    signal: Dict[str, Any]          # sigtrades_core Signal.to_dict
    ownership: str = "user_private"  # platform_shared / user_private
    owner_user_id: Optional[str] = None
    # dev / 已解析：直接携带路由计划；否则 signal-router 向 api-server 解析
    plans: Optional[List[UserRoutePlan]] = None


class RouteOutcome(BaseModel):
    user_id: str
    broker: str
    account_id: Optional[str] = None
    outcome: str   # dispatched / cloud_executed / notified / agent_offline / skipped / error
    detail: Optional[str] = None
