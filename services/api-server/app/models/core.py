"""SaaS 数据模型（PostgreSQL + SQLAlchemy 2.x async）。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), default="")
    language: Mapped[str] = mapped_column(String(8), default="zh")
    auth_provider: Mapped[str] = mapped_column(String(16), default="email")
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verify_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    email_verify_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    password_reset_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    admin_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    sound_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    token_version: Mapped[int] = mapped_column(default=0)
    agent_session_epoch: Mapped[int] = mapped_column(default=0)
    agent_active_device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list["UserMembership"]] = relationship(back_populates="user")
    agent_tokens: Mapped[list["AgentToken"]] = relationship(back_populates="user")


class MembershipPlan(Base):
    __tablename__ = "membership_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    features: Mapped[dict] = mapped_column(JSONB, default=dict)
    stripe_price_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    stripe_price_id_monthly: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    stripe_price_id_yearly: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    price_monthly: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    price_yearly: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    # False = 后台保留、前台定价页不展示；不影响已订阅用户
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def resolve_stripe_price_id(self, billing_interval: str = "monthly") -> Optional[str]:
        interval = (billing_interval or "monthly").lower()
        if interval in ("yearly", "annual", "year"):
            price_id = self.stripe_price_id_yearly
        else:
            price_id = self.stripe_price_id_monthly or self.stripe_price_id
        if not price_id:
            return None
        pid = str(price_id).strip()
        # 拒绝 seed 占位符（price_*_placeholder）与非 Stripe Price ID
        if not pid.startswith("price_") or "placeholder" in pid.lower():
            return None
        return pid


class UserMembership(Base):
    __tablename__ = "user_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("membership_plans.id"))
    status: Mapped[str] = mapped_column(String(32), default="active")
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="memberships")
    plan: Mapped["MembershipPlan"] = relationship()


class AgentToken(Base):
    __tablename__ = "agent_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(64), default="default")
    device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    session_epoch: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="agent_tokens")


class AgentConnectSession(Base):
    __tablename__ = "agent_connect_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    poll_secret_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    pending_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    legacy_callback_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SignalSource(Base):
    __tablename__ = "signal_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    ownership: Mapped[str] = mapped_column(String(32))
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserSourceSubscription(Base):
    __tablename__ = "user_source_subscriptions"
    __table_args__ = (UniqueConstraint("user_id", "source_id", name="uq_user_source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class UserRouteRule(Base):
    __tablename__ = "user_route_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(32), default="auto_trade")
    order_type_policy: Mapped[str] = mapped_column(String(32), default="MKT_only")
    parse_mode: Mapped[str] = mapped_column(String(32), default="example")
    signal_subtype: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    broker: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    account_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    account_label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    default_quantity: Mapped[Optional[int]] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserParseRule(Base):
    __tablename__ = "user_parse_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    parse_mode: Mapped[str] = mapped_column(String(32), default="example")
    priority: Mapped[int] = mapped_column(default=0)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    label: Mapped[str] = mapped_column(String(64), default="default")


class UserBrokerBinding(Base):
    __tablename__ = "user_broker_bindings"
    __table_args__ = (UniqueConstraint("user_id", "label", name="uq_broker_binding_label"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    broker: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(64), default="")
    account_id: Mapped[str] = mapped_column(String(64), default="")
    device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    order_type_policy: Mapped[str] = mapped_column(String(32), default="LMT_then_MKT")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # 非密钥元数据：如 last_probe（测试账户结果）
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class BrokerCredential(Base):
    __tablename__ = "broker_credentials"
    __table_args__ = (UniqueConstraint("user_id", "label", name="uq_broker_cred_label"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    broker: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(64), default="")
    account_id: Mapped[str] = mapped_column(String(64), default="")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    private_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    secrets_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class WebhookIngestToken(Base):
    __tablename__ = "webhook_ingest_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hmac_secret: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(64), default="webhook")


class ExecutionRecord(Base):
    __tablename__ = "execution_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    signal_id: Mapped[str] = mapped_column(String(128), index=True)
    broker: Mapped[str] = mapped_column(String(32))
    account_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    account_label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(64))
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signal: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Discord channel_id / Telegram chat_id，便于按频道统计胜率
    channel_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    signal_subtype: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # 自最新终态回报回写；OPEN 多为空，CLOSE 有值时参与胜率
    realized_pnl: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExecutionReportRow(Base):
    __tablename__ = "execution_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    signal_id: Mapped[str] = mapped_column(String(128), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    broker: Mapped[str] = mapped_column(String(32))
    account_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentPresenceRow(Base):
    __tablename__ = "agent_presence"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    brokers: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserPushToken(Base):
    __tablename__ = "user_push_tokens"
    __table_args__ = (UniqueConstraint("user_id", "fcm_token", name="uq_user_fcm"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    fcm_token: Mapped[str] = mapped_column(String(512))
    platform: Mapped[str] = mapped_column(String(32), default="web")


class PaymentConsentLog(Base):
    __tablename__ = "payment_consent_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    plan_code: Mapped[str] = mapped_column(String(32))
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class RiskDisclosureAgreement(Base):
    """用户风险揭示书同意记录（按文档 version 审计）。"""

    __tablename__ = "risk_disclosure_agreements"
    __table_args__ = (
        UniqueConstraint("user_id", "version", name="uq_risk_disclosure_user_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[str] = mapped_column(String(32), index=True)
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class UserRiskSettings(Base):
    __tablename__ = "user_risk_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    stop_loss_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    take_profit_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    max_position_usd: Mapped[Optional[float]] = mapped_column(nullable=True)
    max_daily_loss_usd: Mapped[Optional[float]] = mapped_column(nullable=True)
    trading_hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="zh")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserGeoEvent(Base):
    """用户 IP / 地域事件（注册、登录）。"""

    __tablename__ = "user_geo_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    country_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    city_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    event_type: Mapped[str] = mapped_column(String(20))  # registration | login
    auth_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InboundEmail(Base):
    """Resend 入站邮件。"""

    __tablename__ = "inbound_emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    resend_email_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    from_address: Mapped[str] = mapped_column(String(1024), default="")
    to_addresses: Mapped[list] = mapped_column(JSONB, default=list)
    cc: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    bcc: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    subject: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, index=True)
    html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    headers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    attachments: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    fetch_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
