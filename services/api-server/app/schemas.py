from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    language: str = "zh"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class GoogleLoginRequest(BaseModel):
    credential: str
    language: str = "zh"


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str = Field(min_length=8)


class VerifyEmailResponse(BaseModel):
    ok: bool
    email: str


class UserProfileUpdate(BaseModel):
    language: Optional[str] = None
    display_name: Optional[str] = Field(default=None, max_length=64)
    sound_notifications: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    language: str
    kill_switch: bool
    sound_notifications: bool = False
    email_verified: bool = False
    auth_provider: str = "email"
    plan_code: Optional[str] = None
    # gift | trial | subscription
    billing_cycle: Optional[str] = None
    risk_disclosure_accepted: bool = False
    risk_disclosure_version: Optional[str] = None


class RiskDisclosureAgreeRequest(BaseModel):
    version: str


class PlanResponse(BaseModel):
    code: str
    name: str
    features: Dict[str, Any]
    stripe_price_id: Optional[str] = None
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_yearly: Optional[str] = None
    price_monthly: Optional[float] = None
    price_yearly: Optional[float] = None


class AgentTokenCreate(BaseModel):
    label: str = "default"


class AgentTokenResponse(BaseModel):
    token: str
    label: str
    message: str = "明文 token 仅返回一次，请妥善保存"


class WebhookTokenCreate(BaseModel):
    label: str = "webhook"
    source_id: Optional[str] = None


class WebhookTokenResponse(BaseModel):
    token: str
    source_id: str
    url_path: str
    message: str = "webhook URL: /ingest/wh/{token}"


class BrokerCredentialCreate(BaseModel):
    broker: str
    account_id: str = ""
    label: str = Field(min_length=1, max_length=64)
    env: Optional[str] = None  # tiger/test ; longbridge/sandbox ; schwab/live ; alpaca/paper|live
    config: Dict[str, Any] = Field(default_factory=dict)
    private_key: Optional[str] = None
    secrets: Optional[Dict[str, str]] = None  # cloud broker API/OAuth secrets


class BrokerCredentialPatch(BaseModel):
    """编辑已保存凭证：仅名称 / 环境，不改密钥。"""

    label: Optional[str] = Field(default=None, min_length=1, max_length=64)
    env: Optional[str] = None


class BrokerBindingCreate(BaseModel):
    broker: str
    label: str = Field(min_length=1, max_length=64)
    account_id: str = ""
    device_id: Optional[str] = None
    order_type_policy: str = "LMT_then_MKT"


class BrokerBindingPatch(BaseModel):
    """编辑 Agent 绑定：名称 / 连接模式（account_id）。"""

    label: Optional[str] = Field(default=None, min_length=1, max_length=64)
    account_id: Optional[str] = None


class PushTokenCreate(BaseModel):
    fcm_token: str = Field(min_length=10)
    platform: str = "web"


class InboundSignalPayload(BaseModel):
    source_id: str
    signal_id: str
    signal: Dict[str, Any]
    ownership: str = "user_private"
    owner_user_id: Optional[str] = None
    plans: Optional[List[Dict[str, Any]]] = None
