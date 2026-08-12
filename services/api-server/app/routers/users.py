from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, get_verified_user
from app.models import (
    AgentToken,
    MembershipPlan,
    SignalSource,
    User,
    UserBrokerBinding,
    WebhookIngestToken,
)
from app.schemas import (
    AgentTokenCreate,
    AgentTokenResponse,
    BrokerBindingCreate,
    BrokerBindingPatch,
    BrokerCredentialCreate,
    BrokerCredentialPatch,
    PlanResponse,
    PushTokenCreate,
    RiskDisclosureAgreeRequest,
    UserProfileUpdate,
    UserResponse,
    WebhookTokenCreate,
    WebhookTokenResponse,
)
from app.services.risk_disclosure import (
    RISK_DISCLOSURE_VERSION,
    latest_agreement,
    load_risk_disclosure_markdown,
    record_agreement,
    user_has_agreed,
)
from app.utils.client_ip import get_client_ip
from app.utils.datetime import format_et
from app.security import generate_webhook_token, hash_agent_token
from app.services.agent_session import issue_agent_token
from app.services.crypto import encrypt
from app.services.entitlements import (
    ensure_within_limit,
    get_active_membership,
    get_active_plan,
)
from app.models import BrokerCredential

router = APIRouter(tags=["users"])


def _billing_cycle_for_user(plan, membership) -> str | None:
    if not plan or plan.code == "free":
        return None
    status = membership.status if membership else "active"
    if status == "trialing":
        return "trial"
    if membership and membership.stripe_subscription_id:
        return "subscription"
    return "gift"


async def _user_response(user: User, plan, membership, db: AsyncSession) -> UserResponse:
    accepted = await user_has_agreed(db, user.id, RISK_DISCLOSURE_VERSION)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        language=user.language,
        kill_switch=user.kill_switch,
        sound_notifications=user.sound_notifications,
        email_verified=user.email_verified,
        auth_provider=user.auth_provider,
        plan_code=plan.code if plan else None,
        billing_cycle=_billing_cycle_for_user(plan, membership),
        risk_disclosure_accepted=accepted,
        risk_disclosure_version=RISK_DISCLOSURE_VERSION if accepted else None,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    req: UserProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.language:
        user.language = req.language[:8]
    if req.display_name is not None:
        user.display_name = req.display_name.strip()[:64] or None
    if req.sound_notifications is not None:
        user.sound_notifications = req.sound_notifications
    await db.commit()
    await db.refresh(user)
    plan = await get_active_plan(db, user.id)
    membership = await get_active_membership(db, user.id)
    return await _user_response(user, plan, membership, db)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    plan = await get_active_plan(db, user.id)
    membership = await get_active_membership(db, user.id)
    return await _user_response(user, plan, membership, db)


@router.get("/risk-disclosure")
async def get_risk_disclosure(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    accepted = await user_has_agreed(db, user.id, RISK_DISCLOSURE_VERSION)
    latest = await latest_agreement(db, user.id, RISK_DISCLOSURE_VERSION) if accepted else None
    try:
        markdown = load_risk_disclosure_markdown()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="risk disclosure document missing") from exc
    return {
        "version": RISK_DISCLOSURE_VERSION,
        "accepted": accepted,
        "agreed_at": format_et(latest.agreed_at) if latest else None,
        "markdown": markdown,
        "read_seconds": 10,
    }


@router.post("/risk-disclosure/agree")
async def agree_risk_disclosure(
    req: RiskDisclosureAgreeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        row = await record_agreement(
            db,
            user.id,
            version=(req.version or "").strip(),
            ip_address=get_client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:512],
            meta={"source": "console_gate"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "version": row.version,
        "agreed_at": format_et(row.agreed_at),
        "accepted": True,
    }


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(MembershipPlan)
        .where(MembershipPlan.is_active.is_(True))
        .order_by(MembershipPlan.sort_order)
    )
    return [
        PlanResponse(
            code=p.code,
            name=p.name,
            features=p.features,
            stripe_price_id=p.stripe_price_id,
            stripe_price_id_monthly=p.stripe_price_id_monthly,
            stripe_price_id_yearly=p.stripe_price_id_yearly,
            price_monthly=float(p.price_monthly) if p.price_monthly is not None else None,
            price_yearly=float(p.price_yearly) if p.price_yearly is not None else None,
        )
        for p in result.scalars().all()
    ]


@router.post("/agent-tokens", response_model=AgentTokenResponse)
async def create_agent_token(
    req: AgentTokenCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    plain = await issue_agent_token(db, user, device_id=None, label=req.label)
    return AgentTokenResponse(token=plain, label=req.label)


@router.post("/webhooks/ingest-token", response_model=WebhookTokenResponse)
async def create_webhook_token(
    req: WebhookTokenCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func as _func

    from app.services.entitlements import ensure_feature

    # 免费版无 Webhook；付费版可创建 / 在已有源下追加 URL
    await ensure_feature(db, user.id, "webhook")

    # 显式 source_id：在已有 Webhook 源下追加 URL（编辑流水线）；否则始终新建独立源（一条流水线一个 source）
    if req.source_id:
        existing_src = (await db.execute(
            select(SignalSource).where(SignalSource.source_id == req.source_id)
        )).scalar_one_or_none()
        if (
            existing_src is None
            or existing_src.owner_user_id != user.id
            or existing_src.kind != "webhook"
        ):
            raise HTTPException(status_code=404, detail="webhook source not found")
        source_id = existing_src.source_id
    else:
        count = (await db.execute(
            select(_func.count()).select_from(SignalSource).where(SignalSource.owner_user_id == user.id)
        )).scalar() or 0
        await ensure_within_limit(db, user.id, "max_signal_sources", count, default=1)
        source_id = f"wh-{uuid.uuid4().hex[:12]}"
        db.add(SignalSource(
            source_id=source_id,
            kind="webhook",
            ownership="user_private",
            owner_user_id=user.id,
            name=req.label,
        ))

    token = generate_webhook_token()
    db.add(WebhookIngestToken(user_id=user.id, token=token, source_id=source_id, label=req.label))
    await db.commit()
    return WebhookTokenResponse(token=token, source_id=source_id, url_path=f"/ingest/wh/{token}")


async def _distinct_broker_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    binding_brokers = (await db.execute(
        select(UserBrokerBinding.broker).where(UserBrokerBinding.user_id == user_id)
    )).scalars().all()
    cred_brokers = (await db.execute(
        select(BrokerCredential.broker).where(BrokerCredential.user_id == user_id)
    )).scalars().all()
    return len(set(binding_brokers) | set(cred_brokers))


async def _upsert_binding_for_account(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    broker: str,
    label: str,
    account_id: str,
    device_id: str | None = None,
    order_type_policy: str = "LMT_then_MKT",
) -> UserBrokerBinding:
    result = await db.execute(
        select(UserBrokerBinding).where(
            UserBrokerBinding.user_id == user_id,
            UserBrokerBinding.label == label,
        )
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        binding = UserBrokerBinding(
            user_id=user_id,
            broker=broker,
            label=label,
            account_id=account_id,
            device_id=device_id,
            order_type_policy=order_type_policy,
            enabled=True,
        )
        db.add(binding)
    else:
        binding.broker = broker
        binding.account_id = account_id
        if device_id is not None:
            binding.device_id = device_id
        binding.order_type_policy = order_type_policy
        binding.enabled = True
    return binding


def _binding_last_probe(binding: UserBrokerBinding) -> dict | None:
    cfg = binding.config if isinstance(binding.config, dict) else {}
    last_probe = cfg.get("last_probe")
    if not isinstance(last_probe, dict):
        return None
    return {
        "ok": bool(last_probe.get("ok")),
        "tested_at": last_probe.get("tested_at"),
        "account_summary": last_probe.get("account_summary"),
        "error": last_probe.get("error"),
        "warning": last_probe.get("warning"),
    }


@router.get("/broker-bindings")
async def list_broker_bindings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(UserBrokerBinding).where(UserBrokerBinding.user_id == user.id)
    )
    rows = []
    for b in result.scalars().all():
        row = {
            "id": str(b.id),
            "broker": b.broker,
            "label": b.label,
            "account_id": b.account_id,
            "device_id": b.device_id,
            "order_type_policy": b.order_type_policy,
            "enabled": b.enabled,
        }
        last_probe = _binding_last_probe(b)
        if last_probe is not None:
            row["last_probe"] = last_probe
        rows.append(row)
    return rows


@router.post("/broker-bindings")
async def create_broker_binding(
    req: BrokerBindingCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    label = req.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="label required")

    dup = await db.execute(
        select(UserBrokerBinding).where(
            UserBrokerBinding.user_id == user.id,
            UserBrokerBinding.label == label,
        )
    )
    existing = dup.scalar_one_or_none()
    if existing is not None and existing.broker != req.broker:
        raise HTTPException(status_code=409, detail="account label already exists")

    dup_cred = await db.execute(
        select(BrokerCredential).where(
            BrokerCredential.user_id == user.id,
            BrokerCredential.label == label,
        )
    )
    if dup_cred.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="account label already exists")

    if existing is None:
        existing_brokers = (await db.execute(
            select(UserBrokerBinding.broker).where(UserBrokerBinding.user_id == user.id)
        )).scalars().all()
        cred_brokers = (await db.execute(
            select(BrokerCredential.broker).where(BrokerCredential.user_id == user.id)
        )).scalars().all()
        distinct_brokers = set(existing_brokers) | set(cred_brokers)
        if req.broker not in distinct_brokers:
            await ensure_within_limit(
                db, user.id, "max_brokers", len(distinct_brokers), default=4
            )

    binding = await _upsert_binding_for_account(
        db,
        user.id,
        broker=req.broker,
        label=label,
        account_id=req.account_id,
        device_id=req.device_id,
        order_type_policy=req.order_type_policy,
    )
    await db.commit()
    await db.refresh(binding)
    return {
        "ok": True,
        "binding": {
            "id": str(binding.id),
            "broker": binding.broker,
            "label": binding.label,
            "account_id": binding.account_id,
            "enabled": binding.enabled,
        },
    }


@router.patch("/broker-bindings/{binding_id}")
async def patch_broker_binding(
    binding_id: uuid.UUID,
    req: BrokerBindingPatch,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑 Agent 绑定：改名称或连接模式（IBKR/富途 preset）。"""
    result = await db.execute(
        select(UserBrokerBinding).where(
            UserBrokerBinding.id == binding_id,
            UserBrokerBinding.user_id == user.id,
        )
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=404, detail="binding not found")

    new_label = (req.label or "").strip() or binding.label
    if new_label != binding.label:
        dup = await db.execute(
            select(UserBrokerBinding).where(
                UserBrokerBinding.user_id == user.id,
                UserBrokerBinding.label == new_label,
                UserBrokerBinding.id != binding.id,
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="account label already exists")
        dup_cred = await db.execute(
            select(BrokerCredential).where(
                BrokerCredential.user_id == user.id,
                BrokerCredential.label == new_label,
            )
        )
        if dup_cred.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="account label already exists")
        binding.label = new_label

    if req.account_id is not None and str(req.account_id).strip():
        binding.account_id = str(req.account_id).strip()

    await db.commit()
    return {
        "ok": True,
        "binding": {
            "id": str(binding.id),
            "broker": binding.broker,
            "label": binding.label,
            "account_id": binding.account_id,
            "device_id": binding.device_id,
            "order_type_policy": binding.order_type_policy,
            "enabled": binding.enabled,
        },
    }


@router.delete("/broker-bindings/{binding_id}")
async def delete_broker_binding(
    binding_id: uuid.UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserBrokerBinding).where(
            UserBrokerBinding.id == binding_id,
            UserBrokerBinding.user_id == user.id,
        )
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=404, detail="binding not found")
    await db.delete(binding)
    await db.commit()
    return {"ok": True}


@router.post("/broker-bindings/{binding_id}/test")
async def test_broker_binding(
    binding_id: uuid.UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """经 Relay → 本地 Agent 探测 IBKR/富途账户（云端不直连券商）。

    探测结果写入 binding.config.last_probe，供下次打开页面回显。
    """
    from datetime import datetime, timezone

    import httpx
    from sqlalchemy.orm.attributes import flag_modified

    from app.config import settings

    result = await db.execute(
        select(UserBrokerBinding).where(
            UserBrokerBinding.id == binding_id,
            UserBrokerBinding.user_id == user.id,
        )
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=404, detail="binding not found")

    broker = (binding.broker or "").strip().lower()
    if broker not in {"ibkr", "futu"}:
        raise HTTPException(status_code=400, detail="only ibkr/futu bindings support agent probe")

    tested_at = datetime.now(timezone.utc).isoformat()

    async def _persist_and_return(payload: dict) -> dict:
        stored = dict(binding.config or {})
        summary = payload.get("account_summary")
        stored["last_probe"] = {
            "ok": bool(payload.get("ok")),
            "tested_at": tested_at,
            "account_summary": summary if isinstance(summary, dict) else None,
            "error": payload.get("error"),
            "warning": payload.get("warning"),
        }
        binding.config = stored
        flag_modified(binding, "config")
        await db.commit()
        out = dict(payload)
        out["tested_at"] = tested_at
        return out

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=30.0) as client:
            resp = await client.post(
                f"{settings.RELAY_GATEWAY_URL.rstrip('/')}/internal/probe-account",
                json={
                    "user_id": str(user.id),
                    "broker": broker,
                    "account_id": binding.account_id or None,
                    "device_id": binding.device_id or None,
                },
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("detail") or detail
            except Exception:  # noqa: BLE001
                pass
            return await _persist_and_return(
                {
                    "ok": False,
                    "broker": broker,
                    "account_id": binding.account_id,
                    "account_summary": None,
                    "error": f"relay probe failed: {detail}",
                }
            )
        payload = resp.json()
    except Exception as e:  # noqa: BLE001
        return await _persist_and_return(
            {
                "ok": False,
                "broker": broker,
                "account_id": binding.account_id,
                "account_summary": None,
                "error": f"relay unreachable: {e}",
            }
        )

    err = payload.get("error")
    if err == "agent_offline":
        err = "本地 Agent 未在线，请先启动并登录 Agent"
    elif err == "probe_timeout":
        err = "Agent 探测超时，请确认 TWS/OpenD 已开启 API"
    elif err == "broker gateway offline":
        err = "券商网关离线，请确认 TWS 或 OpenD 端口可达"
    # Agent 已给出中文诊断（如「端口在监听但握手超时」）时原样透传

    return await _persist_and_return(
        {
            "ok": bool(payload.get("ok")),
            "broker": broker,
            "account_id": payload.get("account_id") or binding.account_id,
            "account_summary": payload.get("account_summary"),
            "error": None if payload.get("ok") else (err or "账户探测失败，请确认 TWS 已登录且 Agent 已重连"),
            "device_id": payload.get("device_id"),
        }
    )


@router.get("/broker-credentials")
async def list_broker_credentials(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.credential_mask import public_credential_row

    result = await db.execute(
        select(BrokerCredential).where(BrokerCredential.user_id == user.id)
        .order_by(BrokerCredential.broker, BrokerCredential.account_id)
    )
    return [public_credential_row(c) for c in result.scalars().all()]


@router.post("/broker-credentials/ibkr-web/generate-keys")
async def generate_ibkr_web_oauth_keys(user: User = Depends(get_verified_user)):
    """一键生成 IBKR Web API OAuth 密钥材料（不落库）。

    DH 2048 生成较慢，放线程池避免阻塞事件循环。
    """
    import asyncio

    from app.services.ibkr_web_keystore import generate_ibkr_oauth_materials

    _ = user  # 需登录
    materials = await asyncio.to_thread(generate_ibkr_oauth_materials)
    return {"ok": True, **materials}


@router.post("/broker-credentials")
async def store_broker_credentials(
    req: BrokerCredentialCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    import json

    from app.services.credential_mask import mask_secret, mask_secret_prefix

    broker = (req.broker or "").strip().lower()
    label = (req.label or "").strip()
    if not label:
        raise HTTPException(status_code=400, detail="label required")

    result = await db.execute(
        select(BrokerCredential).where(
            BrokerCredential.user_id == user.id,
            BrokerCredential.label == label,
        )
    )
    cred = result.scalar_one_or_none()
    is_update = cred is not None

    # 编辑时保留旧 config 中的 hint 等字段，再用请求覆盖
    config = dict(cred.config or {}) if is_update else {}
    config.update(dict(req.config or {}))
    config["label"] = label
    if req.env:
        env = req.env.strip().lower()
        if broker == "tiger":
            # paper/live 仅为标识；API 不走独立 sandbox（模拟盘由账号区分）
            config["env"] = "live" if env in ("production", "prod", "live") else "paper"
            config["sandbox"] = False
            if not config.get("production"):
                config["production"] = {
                    "tiger_id": config.get("tiger_id") or req.config.get("tiger_id"),
                    "account": req.account_id or config.get("account"),
                }
        elif broker == "longbridge":
            config["env"] = "live" if env in ("live", "production", "prod", "online", "线上") else "sandbox"
        elif broker == "schwab":
            config["env"] = "live"
        elif broker == "alpaca":
            config["env"] = "live" if env in ("live", "production", "prod") else "paper"
        elif broker == "ibkr_web":
            config["env"] = "live" if env in ("live", "production", "prod") else "paper"
            if not config.get("realm"):
                config["realm"] = "limited_poa"
            if req.account_id:
                config["account_id"] = req.account_id.strip()

        elif broker == "usmart":
            config["env"] = "uat" if env in ("uat", "test", "sandbox", "paper") else "live"

    enc_pk = None
    enc_secrets = None
    if req.private_key:
        enc_pk = encrypt(req.private_key)
        config["key_hint"] = mask_secret(req.private_key)
    if req.secrets:
        # 编辑时可只提交变更字段：与已存 secrets 合并
        merged_secrets: dict = {}
        if is_update and cred.secrets_encrypted:
            try:
                from app.services.crypto import decrypt

                merged_secrets = json.loads(decrypt(cred.secrets_encrypted))
            except Exception:  # noqa: BLE001
                merged_secrets = {}
        for field, val in (req.secrets or {}).items():
            text = (val or "").strip()
            if text:
                merged_secrets[field] = text
        for field in (
            "app_key",
            "app_secret",
            "access_token",
            "client_id",
            "client_secret",
            "refresh_token",
            "account_hash",
            "api_key",
            "api_secret",
            "phone_number",
            "login_password",
            "trade_password",
            "public_key",
            "private_key",
            "token",
            "consumer_key",
            "access_token_secret",
            "signature_key_pem",
            "encryption_key_pem",
            "dh_prime",
        ):
            val = (merged_secrets.get(field) or "").strip()
            if val:
                if field == "consumer_key":
                    config[f"{field}_hint"] = mask_secret_prefix(val, visible=2)
                else:
                    config[f"{field}_hint"] = mask_secret(val)
        if merged_secrets:
            enc_secrets = encrypt(json.dumps(merged_secrets, ensure_ascii=False))

    has_pk = bool(enc_pk or (is_update and cred.private_key_encrypted))
    has_secrets = bool(enc_secrets or (is_update and cred.secrets_encrypted))

    def _resolved_secrets() -> dict:
        from app.services.crypto import decrypt as _dec

        if enc_secrets:
            return json.loads(_dec(enc_secrets))
        if is_update and cred.secrets_encrypted:
            try:
                return json.loads(_dec(cred.secrets_encrypted))
            except Exception:  # noqa: BLE001
                return {}
        return {}

    if broker == "longbridge" and not has_secrets:
        raise HTTPException(status_code=400, detail="longbridge secrets required")
    if broker == "schwab":
        # Refresh Token / hashValue 由 OAuth 回调写入；表单只要求 Portal 有的字段
        required = ("client_id", "client_secret")
        check = _resolved_secrets()
        missing = [field for field in required if not (check.get(field) or "").strip()]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"schwab secrets required: {', '.join(missing)}",
            )
        if (check.get("refresh_token") or "").strip() and (check.get("account_hash") or "").strip():
            config["oauth_status"] = "authorized"
        else:
            config["oauth_status"] = "pending"
    if broker == "alpaca":
        required = ("api_key", "api_secret")
        check = _resolved_secrets()
        missing = [field for field in required if not (check.get(field) or "").strip()]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"alpaca secrets required: {', '.join(missing)}",
            )
    if broker == "ibkr_web":
        required = (
            "consumer_key",
            "access_token",
            "access_token_secret",
            "signature_key_pem",
            "encryption_key_pem",
            "dh_prime",
        )
        check = _resolved_secrets()
        missing = [field for field in required if not (check.get(field) or "").strip()]
        if missing and not is_update:
            raise HTTPException(
                status_code=400,
                detail=f"ibkr_web secrets required: {', '.join(missing)}",
            )
        if missing and is_update and not has_secrets:
            raise HTTPException(
                status_code=400,
                detail=f"ibkr_web secrets required: {', '.join(missing)}",
            )
        if not (req.account_id or "").strip() and not (cred.account_id if is_update else ""):
            raise HTTPException(status_code=400, detail="ibkr_web account_id required")
    if broker == "usmart":
        channel = str(config.get("channel") or "").strip()
        if not channel:
            raise HTTPException(status_code=400, detail="usmart channel required")
        region_raw = str(config.get("region") or "sg").strip().lower()
        region = "hk" if region_raw in ("hk", "hongkong", "hong kong", "香港") else "sg"
        config["region"] = region
        # 与官网「我的 API」一致：渠道号 + RSA 公私钥；手机/密码为 login 可选补充
        required = ("public_key", "private_key")
        check = _resolved_secrets()
        missing = [field for field in required if not (check.get(field) or "").strip()]
        if missing and not is_update:
            raise HTTPException(
                status_code=400,
                detail=f"usmart secrets required: {', '.join(missing)}",
            )
        if missing and is_update and not has_secrets:
            raise HTTPException(
                status_code=400,
                detail=f"usmart secrets required: {', '.join(missing)}",
            )
        # 区号不暴露给用户填写，按开户站点自动带
        default_area = "852" if region == "hk" else "65"
        config["area_code"] = str(config.get("area_code") or default_area)
    if broker == "tiger":
        if not has_pk:
            raise HTTPException(status_code=400, detail="tiger private_key required")
        license = str(config.get("license") or "TBNZ").strip().upper() or "TBNZ"
        config["license"] = license
        # TBHK 网关要求 Authorization user token；TBNZ 通常不需要
        if license == "TBHK":
            token = (_resolved_secrets().get("token") or "").strip()
            if not token:
                raise HTTPException(
                    status_code=400,
                    detail="TBHK license requires token (upload tiger_openapi_token.properties)",
                )

    dup_binding = await db.execute(
        select(UserBrokerBinding).where(
            UserBrokerBinding.user_id == user.id,
            UserBrokerBinding.label == label,
        )
    )
    existing_binding = dup_binding.scalar_one_or_none()
    if existing_binding is not None and existing_binding.broker != req.broker:
        raise HTTPException(status_code=409, detail="account label already exists")

    if cred is None:
        binding_brokers = (await db.execute(
            select(UserBrokerBinding.broker).where(UserBrokerBinding.user_id == user.id)
        )).scalars().all()
        cred_brokers = (await db.execute(
            select(BrokerCredential.broker).where(BrokerCredential.user_id == user.id)
        )).scalars().all()
        distinct_brokers = set(binding_brokers) | set(cred_brokers)
        if broker not in distinct_brokers:
            await ensure_within_limit(
                db, user.id, "max_brokers", len(distinct_brokers), default=4
            )
        cred = BrokerCredential(
            user_id=user.id,
            broker=req.broker,
            label=label,
            account_id=req.account_id,
        )
        db.add(cred)
    else:
        cred.broker = req.broker
        cred.account_id = req.account_id
    cred.label = label
    cred.config = config
    if enc_pk:
        cred.private_key_encrypted = enc_pk
    if enc_secrets:
        cred.secrets_encrypted = enc_secrets

    await _upsert_binding_for_account(
        db,
        user.id,
        broker=req.broker,
        label=label,
        account_id=req.account_id,
    )
    await db.commit()
    await db.refresh(cred)
    from app.services.credential_mask import public_credential_row
    return {"ok": True, "credential": public_credential_row(cred)}


@router.post("/broker-credentials/{cred_id}/test")
async def test_broker_credential(
    cred_id: uuid.UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """用已保存凭证探测账户资金。

    实际探测在 cloud-executor 执行（装有 tigeropen/longbridge 等 SDK）；
    api-server 只负责鉴权、解密并转发，避免「Tiger API 模块未安装」。
    探测结果写入 credential.config.last_probe，供下次打开页面回显。
    """
    import json
    from datetime import datetime, timezone

    import httpx
    from sqlalchemy.orm.attributes import flag_modified

    from app.config import settings
    from app.services.crypto import decrypt
    from sigtrades_core.brokers import deployment_for

    result = await db.execute(
        select(BrokerCredential).where(
            BrokerCredential.id == cred_id,
            BrokerCredential.user_id == user.id,
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=404, detail="credential not found")

    async def _persist_and_return(payload: dict) -> dict:
        stored = dict(cred.config or {})
        # 去掉可能误写入的明文密钥字段
        for secret_key in (
            "private_key",
            "app_key",
            "app_secret",
            "access_token",
            "client_id",
            "client_secret",
            "refresh_token",
            "account_hash",
            "api_key",
            "api_secret",
            "token",
            "consumer_key",
            "access_token_secret",
            "signature_key_pem",
            "encryption_key_pem",
            "dh_prime",
        ):
            stored.pop(secret_key, None)
        summary = payload.get("account_summary")
        stored["last_probe"] = {
            "ok": bool(payload.get("ok")),
            "tested_at": datetime.now(timezone.utc).isoformat(),
            "account_summary": summary if isinstance(summary, dict) else None,
            "error": payload.get("error"),
        }
        cred.config = stored
        flag_modified(cred, "config")
        await db.commit()
        out = dict(payload)
        out["tested_at"] = stored["last_probe"]["tested_at"]
        return out

    if deployment_for(cred.broker) != "cloud":
        return await _persist_and_return(
            {
                "ok": False,
                "broker": cred.broker,
                "account_summary": None,
                "error": "该券商需通过本地 Agent（IBKR/富途）连接，云端无法直接测账户",
            }
        )

    # 探测用临时 config，勿写回 DB
    probe_config = dict(cred.config or {})
    if cred.account_id and not probe_config.get("account_id"):
        probe_config["account_id"] = cred.account_id
    if cred.private_key_encrypted:
        probe_config["private_key"] = decrypt(cred.private_key_encrypted)
    if cred.secrets_encrypted:
        try:
            probe_config.update(json.loads(decrypt(cred.secrets_encrypted)))
        except Exception as exc:  # noqa: BLE001
            return await _persist_and_return(
                {
                    "ok": False,
                    "broker": cred.broker,
                    "account_summary": None,
                    "error": f"解密凭证失败: {exc}",
                }
            )

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=45.0) as client:
            resp = await client.post(
                f"{settings.CLOUD_EXECUTOR_URL}/internal/probe-account",
                json={"broker": cred.broker, "config": probe_config},
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("detail") or detail
            except Exception:  # noqa: BLE001
                pass
            return await _persist_and_return(
                {
                    "ok": False,
                    "broker": cred.broker,
                    "account_summary": None,
                    "error": f"探测服务失败: {detail}",
                }
            )
        data = resp.json()
        if not isinstance(data, dict):
            data = {"ok": False, "broker": cred.broker, "account_summary": None, "error": "探测返回异常"}
        data.setdefault("broker", cred.broker)
        return await _persist_and_return(data)
    except Exception as exc:  # noqa: BLE001
        return await _persist_and_return(
            {
                "ok": False,
                "broker": cred.broker,
                "account_summary": None,
                "error": f"无法连接探测服务: {exc}",
            }
        )


@router.patch("/broker-credentials/{cred_id}")
async def patch_broker_credential(
    cred_id: uuid.UUID,
    req: BrokerCredentialPatch,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑已保存凭证：仅名称 / 环境标识，不改密钥。"""
    from sqlalchemy.orm.attributes import flag_modified

    from app.services.credential_mask import public_credential_row

    result = await db.execute(
        select(BrokerCredential).where(
            BrokerCredential.id == cred_id,
            BrokerCredential.user_id == user.id,
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=404, detail="credential not found")

    old_label = cred.label
    new_label = (req.label or "").strip() or old_label
    if new_label != old_label:
        dup = await db.execute(
            select(BrokerCredential).where(
                BrokerCredential.user_id == user.id,
                BrokerCredential.label == new_label,
                BrokerCredential.id != cred.id,
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="account label already exists")
        dup_binding = await db.execute(
            select(UserBrokerBinding).where(
                UserBrokerBinding.user_id == user.id,
                UserBrokerBinding.label == new_label,
            )
        )
        existing_binding = dup_binding.scalar_one_or_none()
        if existing_binding is not None and existing_binding.broker != cred.broker:
            raise HTTPException(status_code=409, detail="account label already exists")
        cred.label = new_label
        # 同步关联 binding 的 label（同名绑定）
        bind_result = await db.execute(
            select(UserBrokerBinding).where(
                UserBrokerBinding.user_id == user.id,
                UserBrokerBinding.label == old_label,
            )
        )
        binding = bind_result.scalar_one_or_none()
        if binding is not None:
            binding.label = new_label

    if req.env is not None and str(req.env).strip():
        env = str(req.env).strip().lower()
        broker = (cred.broker or "").strip().lower()
        config = dict(cred.config or {})
        if broker == "tiger":
            config["env"] = "live" if env in ("production", "prod", "live") else "paper"
            config["sandbox"] = False
        elif broker == "longbridge":
            config["env"] = (
                "live" if env in ("live", "production", "prod", "online", "线上") else "sandbox"
            )
        elif broker == "alpaca":
            config["env"] = "live" if env in ("live", "production", "prod") else "paper"
        elif broker == "schwab":
            config["env"] = "live"
        else:
            config["env"] = env
        config["label"] = cred.label
        cred.config = config
        flag_modified(cred, "config")

    await db.commit()
    await db.refresh(cred)
    return {"ok": True, "credential": public_credential_row(cred)}


@router.delete("/broker-credentials/{cred_id}")
async def delete_broker_credential(
    cred_id: uuid.UUID,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BrokerCredential).where(
            BrokerCredential.id == cred_id,
            BrokerCredential.user_id == user.id,
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=404, detail="credential not found")
    bind_result = await db.execute(
        select(UserBrokerBinding).where(
            UserBrokerBinding.user_id == user.id,
            UserBrokerBinding.label == cred.label,
        )
    )
    binding = bind_result.scalar_one_or_none()
    if binding is not None:
        await db.delete(binding)
    await db.delete(cred)
    await db.commit()
    return {"ok": True}


@router.post("/push-token")
async def register_push_token(
    req: PushTokenCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import UserPushToken

    existing = await db.execute(
        select(UserPushToken).where(
            UserPushToken.user_id == user.id,
            UserPushToken.fcm_token == req.fcm_token,
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(UserPushToken(user_id=user.id, fcm_token=req.fcm_token, platform=req.platform))
        await db.commit()
    return {"ok": True}
