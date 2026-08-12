"""启动时建表 + 种子数据（Free/Pro 计划 + demo 用户）。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import (
    AgentToken,
    MembershipPlan,
    SignalSource,
    User,
    UserBrokerBinding,
    UserGeoEvent,
    UserMembership,
    UserRouteRule,
    WebhookIngestToken,
)
from app.security import generate_agent_token, generate_webhook_token, hash_agent_token, hash_password

logger = logging.getLogger(__name__)

# 启动时打印一次，供 e2e / 本地开发使用
DEMO_AGENT_TOKEN: str = ""
DEMO_WEBHOOK_TOKEN: str = ""


async def _apply_light_migrations(conn) -> None:
    """增量列迁移（create_all 不修改已有表，Docker 卷复用时需要）。"""
    from sqlalchemy import text

    for stmt in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR(8) DEFAULT 'zh'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(16) DEFAULT 'email'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verify_token VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verify_expires_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS kill_switch BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS sound_notifications BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(128)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS admin_note TEXT",
        "ALTER TABLE agent_tokens ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ",
        "ALTER TABLE agent_tokens ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ",
        "ALTER TABLE agent_tokens ADD COLUMN IF NOT EXISTS device_id VARCHAR(64)",
        "ALTER TABLE agent_tokens ADD COLUMN IF NOT EXISTS session_epoch INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS agent_session_epoch INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS agent_active_device_id VARCHAR(64)",
        "ALTER TABLE user_memberships ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE user_route_rules ADD COLUMN IF NOT EXISTS parse_mode VARCHAR(32) DEFAULT 'ai'",
        "ALTER TABLE user_route_rules ADD COLUMN IF NOT EXISTS signal_subtype VARCHAR(32)",
        "ALTER TABLE user_route_rules ADD COLUMN IF NOT EXISTS broker VARCHAR(32)",
        "ALTER TABLE user_route_rules ADD COLUMN IF NOT EXISTS account_id VARCHAR(64)",
        "ALTER TABLE broker_credentials ADD COLUMN IF NOT EXISTS secrets_encrypted TEXT",
        "ALTER TABLE broker_credentials ADD COLUMN IF NOT EXISTS label VARCHAR(64)",
        "ALTER TABLE user_broker_bindings ADD COLUMN IF NOT EXISTS device_id VARCHAR(64)",
        "ALTER TABLE user_broker_bindings ADD COLUMN IF NOT EXISTS enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE user_broker_bindings ADD COLUMN IF NOT EXISTS label VARCHAR(64)",
        "ALTER TABLE user_broker_bindings ADD COLUMN IF NOT EXISTS config JSONB DEFAULT '{}'::jsonb",
        "ALTER TABLE user_route_rules ADD COLUMN IF NOT EXISTS account_label VARCHAR(64)",
        "ALTER TABLE user_route_rules ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE execution_reports ADD COLUMN IF NOT EXISTS user_id UUID",
        "ALTER TABLE user_risk_settings ADD COLUMN IF NOT EXISTS max_daily_loss_usd DOUBLE PRECISION",
        "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS stripe_price_id_monthly VARCHAR(128)",
        "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS stripe_price_id_yearly VARCHAR(128)",
        "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS price_monthly NUMERIC(10,2)",
        "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS price_yearly NUMERIC(10,2)",
        "ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE promotions ADD COLUMN IF NOT EXISTS partner_external_ref VARCHAR(128)",
        "ALTER TABLE promotions ADD COLUMN IF NOT EXISTS parent_promotion_id UUID",
        "ALTER TABLE promotions ADD COLUMN IF NOT EXISTS membership_period_end TIMESTAMPTZ",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_promotions_partner_external_ref "
        "ON promotions (partner_external_ref) WHERE partner_external_ref IS NOT NULL",
    ):
        await conn.execute(text(stmt))


PLANS = [
    {
        "code": "free",
        "name": "Free",
        "features": {
            "auto_trade": False,
            "webhook": False,
            "max_signal_sources": 1,
            "max_brokers": 1,
            "max_discord_channels": 1,
            "discord_multi_channel": False,
            "ai_parse": True,
            "multi_agent": False,
        },
        "sort_order": 0,
    },
    {
        "code": "starter",
        "name": "Starter",
        "features": {
            "auto_trade": False,
            "webhook": True,
            "max_signal_sources": 5,
            "max_brokers": 2,
            "max_discord_channels": 1,
            "discord_multi_channel": False,
            "ai_parse": True,
            "multi_agent": False,
        },
        "sort_order": 1,
        "price_monthly": 19.0,
        "price_yearly": 190.0,
        # Stripe Price ID 由后台「会员方案」配置，勿在此写 placeholder（会覆盖生产配置）
        "stripe_price_id_monthly": None,
        "stripe_price_id_yearly": None,
    },
    {
        "code": "pro",
        "name": "Pro",
        "features": {
            "auto_trade": True,
            "webhook": True,
            "max_signal_sources": 10,
            "max_brokers": 10,
            "max_discord_channels": 20,
            "discord_multi_channel": True,
            "ai_parse": True,
            "multi_agent": True,
        },
        "sort_order": 2,
        "price_monthly": 29.0,
        "price_yearly": 290.0,
        "stripe_price_id_monthly": None,
        "stripe_price_id_yearly": None,
    },
]


async def _reparse_geo_events_from_ip(db) -> None:
    """用 mmdb 补全已有 geo 事件中缺失的 country_code / 省份（装库前写入的记录）。"""
    from app.services.geoip_service import country_and_city_from_ip

    rows = (await db.execute(select(UserGeoEvent))).scalars().all()
    updated = 0
    for g in rows:
        ip = (g.ip_address or "").strip()
        if not ip:
            continue
        cc, region = country_and_city_from_ip(ip)
        changed = False
        if cc and not g.country_code:
            g.country_code = cc
            changed = True
        if region and not (g.city_name or "").strip():
            g.city_name = region[:200]
            changed = True
        if changed:
            updated += 1
    if updated:
        await db.commit()
        logger.info("Geo reparse from IP: updated %d events", updated)


async def _backfill_missing_registration_geo(db) -> None:
    """仅 SEED_DEMO：给仍无 registration 事件的用户补 Local Dev 占位（勿用于生产真实用户）。"""
    if not settings.SEED_DEMO:
        return
    from sqlalchemy import exists

    has_reg = exists(
        select(1)
        .select_from(UserGeoEvent)
        .where(UserGeoEvent.user_id == User.id, UserGeoEvent.event_type == "registration")
    )
    result = await db.execute(select(User).where(~has_reg))
    users = result.scalars().all()
    for u in users:
        db.add(UserGeoEvent(
            user_id=u.id,
            ip_address="127.0.0.1",
            country_code="US",
            city_name="Local Dev",
            event_type="registration",
            auth_method="seed",
        ))
    if users:
        await db.commit()
        logger.info("Geo backfill: %d users without registration geo", len(users))


async def _run_alembic_upgrade() -> None:
    """生产环境增量 schema；baseline 会跳过已存在表。"""
    import asyncio
    from pathlib import Path

    try:
        from alembic import command
        from alembic.config import Config

        ini = Path(__file__).resolve().parents[2] / "alembic.ini"
        if not ini.is_file():
            return
        cfg = Config(str(ini))

        def _upgrade():
            command.upgrade(cfg, "head")

        await asyncio.to_thread(_upgrade)
        logger.info("Alembic upgrade head completed")
    except Exception as e:  # noqa: BLE001
        logger.debug("Alembic upgrade skipped: %s", e)


async def _ensure_plans(db) -> None:
    """同步种子计划（新增档位 + 更新权益字段）。"""
    for p in PLANS:
        result = await db.execute(select(MembershipPlan).where(MembershipPlan.code == p["code"]))
        plan = result.scalar_one_or_none()
        if plan is None:
            db.add(MembershipPlan(
                code=p["code"],
                name=p["name"],
                features=p["features"],
                sort_order=p.get("sort_order", 0),
                price_monthly=p.get("price_monthly"),
                price_yearly=p.get("price_yearly"),
                stripe_price_id=p.get("stripe_price_id_monthly"),
                stripe_price_id_monthly=p.get("stripe_price_id_monthly"),
                stripe_price_id_yearly=p.get("stripe_price_id_yearly"),
            ))
        else:
            plan.name = p["name"]
            plan.features = dict(p["features"])
            plan.sort_order = p.get("sort_order", plan.sort_order)
            if plan.price_monthly is None and p.get("price_monthly") is not None:
                plan.price_monthly = p["price_monthly"]
            if plan.price_yearly is None and p.get("price_yearly") is not None:
                plan.price_yearly = p["price_yearly"]
            # 仅在库内为空/占位符时回填；已配置的真实 Stripe Price ID 绝不覆盖
            seed_m = p.get("stripe_price_id_monthly")
            seed_y = p.get("stripe_price_id_yearly")
            cur_m = (plan.stripe_price_id_monthly or plan.stripe_price_id or "").strip()
            cur_y = (plan.stripe_price_id_yearly or "").strip()
            if seed_m and (not cur_m or "placeholder" in cur_m.lower()):
                plan.stripe_price_id_monthly = seed_m
                plan.stripe_price_id = seed_m
            if seed_y and (not cur_y or "placeholder" in cur_y.lower()):
                plan.stripe_price_id_yearly = seed_y
            # 清掉历史 placeholder，避免 checkout 误用
            if cur_m and "placeholder" in cur_m.lower() and not seed_m:
                plan.stripe_price_id_monthly = None
                if (plan.stripe_price_id or "").strip() == cur_m:
                    plan.stripe_price_id = None
            if cur_y and "placeholder" in cur_y.lower() and not seed_y:
                plan.stripe_price_id_yearly = None
    await db.commit()


async def _patch_plan_features(db) -> None:
    """同步种子计划权益（已有 Docker 卷中的 plan 行不会随 PLANS 常量自动更新）。"""
    desired = {p["code"]: p["features"] for p in PLANS}
    result = await db.execute(select(MembershipPlan))
    changed = 0
    for plan in result.scalars().all():
        target = desired.get(plan.code)
        if not target:
            continue
        merged = dict(plan.features or {})
        patched = False
        for key, val in target.items():
            if merged.get(key) != val:
                merged[key] = val
                patched = True
        if patched:
            plan.features = merged
            changed += 1
    if changed:
        await db.commit()
        logger.info("Patched membership plan features for %d plan(s)", changed)


async def init_db() -> None:
    global DEMO_AGENT_TOKEN, DEMO_WEBHOOK_TOKEN

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_light_migrations(conn)

    await _run_alembic_upgrade()

    if settings.SEED_DEMO:
        async with SessionLocal() as db:
            for p in PLANS:
                existing = await db.execute(select(MembershipPlan).where(MembershipPlan.code == p["code"]))
                if existing.scalar_one_or_none() is None:
                    db.add(MembershipPlan(
                        code=p["code"],
                        name=p["name"],
                        features=p["features"],
                        sort_order=p.get("sort_order", 0),
                        stripe_price_id=p.get("stripe_price_id_monthly"),
                        stripe_price_id_monthly=p.get("stripe_price_id_monthly"),
                        stripe_price_id_yearly=p.get("stripe_price_id_yearly"),
                    ))

            demo = await db.execute(select(User).where(User.email == "demo@sigtrades.app"))
            user = demo.scalar_one_or_none()
            if user is None:
                user = User(
                    email="demo@sigtrades.app",
                    password_hash=hash_password("demo1234"),
                    language="zh",
                    email_verified=True,
                    auth_provider="email",
                )
                db.add(user)
                await db.flush()

                free_plan = await db.execute(select(MembershipPlan).where(MembershipPlan.code == "free"))
                plan = free_plan.scalar_one()
                db.add(UserMembership(user_id=user.id, plan_id=plan.id, status="active"))

                source_id = f"wh-{user.id.hex[:12]}"
                db.add(SignalSource(
                    source_id=source_id,
                    kind="webhook",
                    ownership="user_private",
                    owner_user_id=user.id,
                    name="Demo Webhook Source",
                ))
                db.add(UserRouteRule(
                    user_id=user.id,
                    source_id=source_id,
                    action="auto_trade",
                    order_type_policy="MKT_only",
                ))
                db.add(UserBrokerBinding(
                    user_id=user.id,
                    broker="ibkr",
                    label="demo-acc",
                    account_id="demo-acc",
                    order_type_policy="MKT_only",
                ))

                wh_token = generate_webhook_token()
                DEMO_WEBHOOK_TOKEN = wh_token
                db.add(WebhookIngestToken(
                    user_id=user.id,
                    token=wh_token,
                    source_id=source_id,
                    label="demo",
                ))

                user.agent_session_epoch = 1
                agent_plain = generate_agent_token()
                DEMO_AGENT_TOKEN = agent_plain
                db.add(AgentToken(
                    user_id=user.id,
                    token_hash=hash_agent_token(agent_plain),
                    label="demo-agent",
                    session_epoch=1,
                ))

                logger.info("Demo user seeded: demo@sigtrades.app / demo1234")
                logger.info("Demo agent token (save now): %s", agent_plain)
                logger.info("Demo webhook token: %s", wh_token)

            curated = await db.execute(select(SignalSource).where(SignalSource.source_id == "platform-discord-demo"))
            if curated.scalar_one_or_none() is None:
                db.add(SignalSource(
                    source_id="platform-discord-demo",
                    kind="discord",
                    ownership="platform_shared",
                    name="Demo Curated Discord",
                    config={"channel_ids": [], "description": "Admin: add channel IDs after bot joins source server"},
                ))

            await db.commit()

    async with SessionLocal() as db:
        await _ensure_plans(db)

    async with SessionLocal() as db:
        from app.services.promotion_redeem import ensure_default_sunnyquant_campaign

        await ensure_default_sunnyquant_campaign(db)

    async with SessionLocal() as db:
        await _reparse_geo_events_from_ip(db)
        await _backfill_missing_registration_geo(db)

    async with SessionLocal() as db:
        from app.services.promotion_redeem import backfill_partner_gift_period_ends

        await backfill_partner_gift_period_ends(db)
