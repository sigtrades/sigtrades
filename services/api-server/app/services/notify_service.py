"""通知投递：邮件 + 可选 Webhook / FCM 推送（不再落库通知记录）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User, UserPushToken
from app.services.confirm_trade_service import action_urls, issue_action_token
from app.services.email_service import send_notify_email, send_pending_confirm_email
from app.services.fcm_service import fcm_enabled, send_fcm_to_tokens

logger = logging.getLogger(__name__)

# 不发邮件的 kind（省配额；Agent 上线看控制台即可）
_EMAIL_SKIP_KINDS = frozenset({"agent_ok"})

# kind -> (subject, title, body) 中英
_TEMPLATES = {
    "agent_offline": {
        "zh": ("Agent 离线", "Agent 已离线", "您的 Relay Agent 已离线，自动交易信号可能无法执行。请在本机打开 Agent 并保持在线。"),
        "en": ("Agent offline", "Agent offline", "Your Relay Agent went offline. Auto-trade signals may not execute. Please start the Agent on your computer."),
    },
    "agent_ok": {
        "zh": ("Agent 已上线", "Agent 已上线", "您的 Relay Agent 已成功连接。"),
        "en": ("Agent online", "Agent online", "Your Relay Agent is connected."),
    },
    "signal": {
        "zh": ("新信号", "收到新交易信号", "系统收到一条新交易信号，可在控制台查看详情。"),
        "en": ("New signal", "New trading signal", "A new trading signal was received. Open the dashboard for details."),
    },
    "execution": {
        "zh": ("执行回执", "交易执行状态更新", "有一条交易执行状态已更新，请在控制台查看。"),
        "en": ("Execution update", "Execution status updated", "A trade execution status was updated. Check the dashboard."),
    },
    "parse_failed": {
        "zh": ("解析失败", "信号解析失败", "有一条信号未能解析为有效交易指令，未自动下单。"),
        "en": ("Parse failed", "Signal parse failed", "A signal could not be parsed into a valid trade and was not auto-traded."),
    },
    "risk_blocked": {
        "zh": ("风控拦截", "信号被风控拦截", "有一条信号因风控规则被拦截，未自动下单。"),
        "en": ("Risk blocked", "Signal blocked by risk rules", "A signal was blocked by risk rules and not auto-traded."),
    },
    "entitlement_blocked": {
        "zh": ("信号未执行", "权益/急停限制", "有一条信号因会员权益或急停限制未自动下单（如已达每日上限或已开启急停）。"),
        "en": ("Signal not executed", "Plan limit or kill switch", "A signal was not auto-traded due to plan limits or kill switch."),
    },
    "protective_failed": {
        "zh": ("保护单失败", "止损/止盈下单失败", "主单已成交，但止损/止盈保护单下单失败，请立即手动检查持仓并设置保护。"),
        "en": ("Protective order failed", "Stop-loss / take-profit failed", "Main order filled but protective orders failed. Check the position and set protection manually."),
    },
    "idempotency_unavailable": {
        "zh": ("信号暂缓", "系统繁忙，信号暂未下单", "系统繁忙未能确认幂等状态，本条信号暂未自动下单。请稍后重试或检查控制台。"),
        "en": ("Signal deferred", "Signal deferred", "Could not verify idempotency; this signal was not auto-traded. Retry later or check the dashboard."),
    },
    "pending_confirm": {
        "zh": ("待确认交易", "需要您确认后才会下单", "有一条信号等待您确认后才会下单。"),
        "en": ("Confirm trade", "Confirmation required", "A signal is waiting for your confirmation before trading."),
    },
}


def _lang(language: str) -> str:
    return "en" if (language or "").lower().startswith("en") else "zh"


def _signal_fields(payload: Dict[str, Any]) -> Dict[str, str]:
    signal = payload.get("signal") if isinstance(payload.get("signal"), dict) else {}
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    meta = signal.get("metadata") if isinstance(signal.get("metadata"), dict) else {}
    sq = meta.get("sunnyquant") if isinstance(meta.get("sunnyquant"), dict) else {}
    return {
        "title": str(sq.get("title") or "").strip(),
        "symbol": str(signal.get("symbol") or signal.get("ticker") or "").strip() or "-",
        "side": str(signal.get("side") or signal.get("action") or "").strip() or "-",
        "qty": str(signal.get("qty") or signal.get("quantity") or signal.get("size") or "").strip() or "-",
        "order_type": str(signal.get("order_type") or signal.get("type") or "").strip() or "-",
        "broker": str(extra.get("broker") or "").strip() or "-",
        "account": str(extra.get("account_label") or extra.get("account_id") or "").strip() or "-",
        "reason": str(extra.get("reason") or "").strip(),
        "status": str(extra.get("status") or payload.get("status") or "").strip(),
        "signal_id": str(payload.get("signal_id") or signal.get("signal_id") or "").strip(),
        "source_id": str(payload.get("source_id") or "").strip(),
    }


def _summary_lines(kind: str, payload: Dict[str, Any], lang: str) -> List[str]:
    f = _signal_fields(payload)
    en = lang == "en"
    lines: List[str] = []

    def add(label_zh: str, label_en: str, value: str) -> None:
        if not value or value == "-":
            return
        if en:
            lines.append(f"{label_en}: {value}")
        else:
            lines.append(f"{label_zh}：{value}")

    # 信号类摘要
    if kind in {
        "agent_offline",
        "signal",
        "execution",
        "parse_failed",
        "risk_blocked",
        "entitlement_blocked",
        "protective_failed",
        "idempotency_unavailable",
        "pending_confirm",
    }:
        add("标题", "Title", f["title"])
        add("标的", "Symbol", f["symbol"])
        add("方向", "Side", f["side"])
        add("数量", "Qty", f["qty"])
        add("订单类型", "Order type", f["order_type"])
        add("券商", "Broker", f["broker"])
        add("账户", "Account", f["account"])
        add("状态", "Status", f["status"])
        add("原因", "Reason", f["reason"])
        if f["signal_id"]:
            add("信号 ID", "Signal ID", f["signal_id"])
    return lines


def _pending_summary_lines(payload: Dict[str, Any], lang: str) -> list[str]:
    return _summary_lines("pending_confirm", payload, lang)


async def _send_pending_confirm_email(
    user: User,
    *,
    lang: str,
    payload: Dict[str, Any],
) -> None:
    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    signal_id = str(payload.get("signal_id") or "")
    source_id = str(payload.get("source_id") or "")
    if not signal_id or not source_id:
        logger.warning("pending_confirm missing signal_id/source_id, skip email buttons")
        return

    account_label = str(extra.get("account_label") or "").strip()
    confirm_token = issue_action_token(
        user_id=user.id,
        signal_id=signal_id,
        source_id=source_id,
        action="confirm",
        account_label=account_label,
        broker=str(extra.get("broker") or ""),
        account_id=str(extra.get("account_id") or ""),
    )
    reject_token = issue_action_token(
        user_id=user.id,
        signal_id=signal_id,
        source_id=source_id,
        action="reject",
        account_label=account_label,
        broker=str(extra.get("broker") or ""),
        account_id=str(extra.get("account_id") or ""),
    )
    confirm_url, reject_url = action_urls(
        confirm_token=confirm_token, reject_token=reject_token
    )
    await asyncio.to_thread(
        send_pending_confirm_email,
        user.email,
        confirm_url=confirm_url,
        reject_url=reject_url,
        summary_lines=_pending_summary_lines(payload, lang),
        lang=lang,
    )


async def deliver(
    db: AsyncSession,
    *,
    user_id,
    kind: str,
    language: str,
    payload: Dict[str, Any],
) -> None:
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        return

    lang = _lang(language or user.language)
    if kind == "pending_confirm" and kind not in _EMAIL_SKIP_KINDS:
        try:
            await _send_pending_confirm_email(user, lang=lang, payload=payload)
        except Exception as e:  # noqa: BLE001
            logger.warning("pending_confirm email failed: %s", e)
    elif kind not in _EMAIL_SKIP_KINDS:
        tpl = _TEMPLATES.get(kind) or _TEMPLATES["signal"]
        subject, title, body = tpl.get(lang, tpl["zh"])
        # 未知 kind：标题用 kind，正文用通用说明
        if kind not in _TEMPLATES:
            if lang == "en":
                subject, title, body = (
                    f"Notification — {kind}",
                    "Notification",
                    "You have a new notification from sigtrades.",
                )
            else:
                subject, title, body = (
                    f"通知 — {kind}",
                    "系统通知",
                    "您有一条来自 sigtrades 的新通知。",
                )
        await asyncio.to_thread(
            send_notify_email,
            user.email,
            subject=subject,
            title=title,
            body=body,
            summary_lines=_summary_lines(kind, payload, lang),
            lang=lang,
        )

    if settings.NOTIFY_PUSH_WEBHOOK:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(settings.NOTIFY_PUSH_WEBHOOK, json={
                    "user_id": str(user_id),
                    "kind": kind,
                    "language": lang,
                    "payload": payload,
                })
        except Exception as e:  # noqa: BLE001
            logger.warning("push webhook failed: %s", e)

    await _send_fcm(db, user_id, kind, lang, payload)


async def _send_fcm(db: AsyncSession, user_id, kind: str, lang: str, payload: Dict[str, Any]) -> None:
    """Firebase Cloud Messaging HTTP v1 API。"""
    if not fcm_enabled():
        return

    extra = payload.get("extra") if isinstance(payload.get("extra"), dict) else {}
    tokens: list[str] = []
    if payload.get("fcm_token"):
        tokens.append(payload["fcm_token"])
    elif extra.get("fcm_token"):
        tokens.append(extra["fcm_token"])
    else:
        result = await db.execute(select(UserPushToken.fcm_token).where(UserPushToken.user_id == user_id))
        tokens = [row[0] for row in result.all()]
    if not tokens:
        return

    tpl = _TEMPLATES.get(kind, _TEMPLATES.get("signal"))
    if tpl:
        subject, _title, body = tpl.get(lang, tpl["zh"])
    else:
        subject, body = ("sigtrades", kind)

    _, stale = await send_fcm_to_tokens(
        tokens,
        title=subject,
        body=body,
        data={"kind": kind, "payload": str(payload)[:512]},
    )
    if stale:
        await db.execute(
            delete(UserPushToken).where(
                UserPushToken.user_id == user_id,
                UserPushToken.fcm_token.in_(stale),
            )
        )
        await db.flush()
