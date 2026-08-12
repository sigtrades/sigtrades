"""管理员 — 运营统计。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    AgentPresenceRow,
    ExecutionRecord,
    PaymentConsentLog,
    SignalSource,
    User,
    UserGeoEvent,
    UserMembership,
)
from app.routers.admin.deps import verify_admin_token
from app.utils.datetime import et_day_start_utc, format_et, to_et

router = APIRouter()


def _date_key(dt: datetime) -> str:
    et = to_et(dt)
    assert et is not None
    return et.strftime("%Y-%m-%d")


@router.get("/overview")
async def analytics_overview(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    banned_users = (
        await db.execute(select(func.count(User.id)).where(User.is_banned.is_(True)))
    ).scalar() or 0
    kill_switch_users = (
        await db.execute(select(func.count(User.id)).where(User.kill_switch.is_(True)))
    ).scalar() or 0
    active_memberships = (
        await db.execute(
            select(func.count(UserMembership.id)).where(UserMembership.status == "active")
        )
    ).scalar() or 0
    agents_online = (
        await db.execute(
            select(func.count(AgentPresenceRow.user_id)).where(AgentPresenceRow.online.is_(True))
        )
    ).scalar() or 0

    day_start = et_day_start_utc()
    executions_today = (
        await db.execute(
            select(func.count(ExecutionRecord.id)).where(ExecutionRecord.created_at >= day_start)
        )
    ).scalar() or 0

    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_users_7d = (
        await db.execute(select(func.count(User.id)).where(User.created_at >= week_ago))
    ).scalar() or 0
    new_users_today = (
        await db.execute(select(func.count(User.id)).where(User.created_at >= day_start))
    ).scalar() or 0
    payment_consents = (
        await db.execute(select(func.count(PaymentConsentLog.id)))
    ).scalar() or 0

    from app.services.subscription_payment_analytics import build_subscription_payment_stats

    pay_stats = await build_subscription_payment_stats(db, days=14)

    return {
        "success": True,
        "data": {
            "current_time_et": format_et(datetime.now(timezone.utc)),
            "total_users": int(total_users),
            "banned_users": int(banned_users),
            "kill_switch_users": int(kill_switch_users),
            "active_memberships": int(active_memberships),
            "agents_online": int(agents_online),
            "executions_today": int(executions_today),
            "new_users_7d": int(new_users_7d),
            "new_users_today": int(new_users_today),
            "payment_consents": int(payment_consents),
            # 付费数据
            "paid_memberships": int(pay_stats.get("paid_memberships") or 0),
            "gift_memberships": int(pay_stats.get("gift_memberships") or 0),
            "trial_memberships": int(pay_stats.get("trial_memberships") or 0),
            "paid_checkout_count": int(pay_stats.get("paid_checkout_count") or 0),
            "total_paid_amount_usd": float(pay_stats.get("total_paid_amount_usd") or 0),
            "today_paid_count": int(pay_stats.get("today_paid_count") or 0),
            "today_paid_amount_usd": float(pay_stats.get("today_paid_amount_usd") or 0),
            "payments_by_day": pay_stats.get("payments_by_day") or [],
        },
    }


@router.get("/users/trends")
async def users_trends(
    days: int = Query(30, ge=7, le=365),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    end_utc = et_day_start_utc() + timedelta(days=1)
    start_utc = end_utc - timedelta(days=days)
    start_et = to_et(start_utc)
    end_et = to_et(end_utc - timedelta(seconds=1))
    assert start_et and end_et

    day_keys = []
    cursor = start_et.replace(hour=0, minute=0, second=0, microsecond=0)
    while cursor.date() <= end_et.date():
        day_keys.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)

    reg_counts = {d: 0 for d in day_keys}
    users = (
        await db.execute(
            select(User.created_at).where(User.created_at >= start_utc, User.created_at < end_utc)
        )
    ).scalars().all()
    for created_at in users:
        key = _date_key(created_at)
        if key in reg_counts:
            reg_counts[key] += 1

    login_counts = {d: 0 for d in day_keys}
    login_rows = (
        await db.execute(
            select(UserGeoEvent.created_at, UserGeoEvent.user_id).where(
                UserGeoEvent.event_type == "login",
                UserGeoEvent.created_at >= start_utc,
                UserGeoEvent.created_at < end_utc,
            )
        )
    ).all()
    seen_by_day: dict[str, set] = {d: set() for d in day_keys}
    for created_at, user_id in login_rows:
        key = _date_key(created_at)
        if key in seen_by_day:
            seen_by_day[key].add(user_id)
    for d in day_keys:
        login_counts[d] = len(seen_by_day[d])

    total_before = (
        await db.execute(select(func.count(User.id)).where(User.created_at < start_utc))
    ).scalar() or 0
    cumulative = total_before
    cumulative_by_day = []
    for d in day_keys:
        cumulative += reg_counts[d]
        cumulative_by_day.append({"date": d, "count": cumulative})

    return {
        "success": True,
        "data": {
            "days": days,
            "from_date": day_keys[0] if day_keys else None,
            "to_date": day_keys[-1] if day_keys else None,
            "registrations_by_day": [{"date": d, "count": reg_counts[d]} for d in day_keys],
            "dau_by_day": [{"date": d, "count": login_counts[d]} for d in day_keys],
            "cumulative_users_by_day": cumulative_by_day,
        },
    }


def _channel_label(config: dict[str, Any] | None, channel_id: str) -> str:
    if not channel_id:
        return "（无频道 / Webhook）"
    if not isinstance(config, dict):
        return channel_id
    labels = config.get("channel_labels") or config.get("chat_labels") or {}
    if isinstance(labels, dict):
        label = labels.get(channel_id) or labels.get(str(channel_id))
        if label:
            return str(label)
    return channel_id


def _win_rate(wins: int, losses: int) -> float | None:
    denom = wins + losses
    if denom <= 0:
        return None
    return round(wins / denom, 4)


@router.get("/channel-stats")
async def channel_stats(
    days: int = Query(90, ge=1, le=730),
    source_id: Optional[str] = None,
    kind: Optional[str] = Query(None, description="discord|telegram|webhook"),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    """按 (source_id, channel_id) 统计胜率。

    口径：仅统计有 realized_pnl 的成交；同一 signal_id 多券商先合并 PnL 再计 1 笔；
    OPEN 无 PnL 不进胜率分母。
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    params: dict[str, Any] = {"since": since}
    filters = ["er.created_at >= :since"]
    if source_id:
        filters.append("er.source_id = :source_id")
        params["source_id"] = source_id
    if kind:
        filters.append("ss.kind = :kind")
        params["kind"] = kind.lower()

    where_sql = " AND ".join(filters)
    sql = text(
        f"""
        WITH closed AS (
          SELECT
            er.source_id,
            COALESCE(er.channel_id, '') AS channel_id,
            er.signal_id,
            SUM(er.realized_pnl)::double precision AS pnl
          FROM execution_records er
          LEFT JOIN signal_sources ss ON ss.source_id = er.source_id
          WHERE er.realized_pnl IS NOT NULL
            AND {where_sql}
          GROUP BY er.source_id, COALESCE(er.channel_id, ''), er.signal_id
        ),
        opens AS (
          SELECT
            er.source_id,
            COALESCE(er.channel_id, '') AS channel_id,
            COUNT(DISTINCT er.signal_id) AS open_signals
          FROM execution_records er
          LEFT JOIN signal_sources ss ON ss.source_id = er.source_id
          WHERE UPPER(COALESCE(er.signal_subtype, '')) = 'OPEN'
            AND {where_sql}
          GROUP BY er.source_id, COALESCE(er.channel_id, '')
        ),
        agg AS (
          SELECT
            source_id,
            channel_id,
            COUNT(*)::int AS closed_trades,
            COUNT(*) FILTER (WHERE pnl > 0)::int AS wins,
            COUNT(*) FILTER (WHERE pnl < 0)::int AS losses,
            COUNT(*) FILTER (WHERE pnl = 0)::int AS breakeven,
            COALESCE(SUM(pnl), 0)::double precision AS total_pnl
          FROM closed
          GROUP BY source_id, channel_id
        )
        SELECT
          COALESCE(a.source_id, o.source_id) AS source_id,
          COALESCE(a.channel_id, o.channel_id) AS channel_id,
          COALESCE(a.closed_trades, 0) AS closed_trades,
          COALESCE(a.wins, 0) AS wins,
          COALESCE(a.losses, 0) AS losses,
          COALESCE(a.breakeven, 0) AS breakeven,
          COALESCE(a.total_pnl, 0) AS total_pnl,
          COALESCE(o.open_signals, 0) AS open_signals,
          ss.name AS source_name,
          ss.kind AS source_kind,
          ss.config AS source_config
        FROM agg a
        FULL OUTER JOIN opens o
          ON o.source_id = a.source_id AND o.channel_id = a.channel_id
        LEFT JOIN signal_sources ss
          ON ss.source_id = COALESCE(a.source_id, o.source_id)
        ORDER BY COALESCE(a.closed_trades, 0) DESC, COALESCE(a.total_pnl, 0) DESC
        """
    )
    rows = (await db.execute(sql, params)).mappings().all()
    items = []
    for r in rows:
        wins = int(r["wins"] or 0)
        losses = int(r["losses"] or 0)
        channel = str(r["channel_id"] or "")
        config = r["source_config"] if isinstance(r["source_config"], dict) else {}
        items.append(
            {
                "source_id": r["source_id"],
                "source_name": r["source_name"] or r["source_id"],
                "source_kind": r["source_kind"] or "",
                "channel_id": channel or None,
                "channel_label": _channel_label(config, channel),
                "closed_trades": int(r["closed_trades"] or 0),
                "wins": wins,
                "losses": losses,
                "breakeven": int(r["breakeven"] or 0),
                "open_signals": int(r["open_signals"] or 0),
                "total_pnl": round(float(r["total_pnl"] or 0), 4),
                "win_rate": _win_rate(wins, losses),
            }
        )

    return {
        "success": True,
        "data": {
            "days": days,
            "definition": {
                "unit": "signal_id after merging multi-broker realized_pnl",
                "win": "merged realized_pnl > 0",
                "exclude": "OPEN / fills without realized_pnl",
            },
            "items": items,
        },
    }


@router.get("/channel-stats/detail")
async def channel_stats_detail(
    source_id: str = Query(...),
    channel_id: Optional[str] = Query(None, description="空字符串表示无频道"),
    days: int = Query(90, ge=1, le=730),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    """某频道按用户拆分的胜率详情。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    channel_key = "" if channel_id is None else channel_id
    params = {"since": since, "source_id": source_id, "channel_id": channel_key}
    sql = text(
        """
        WITH closed AS (
          SELECT
            er.user_id,
            er.signal_id,
            SUM(er.realized_pnl)::double precision AS pnl
          FROM execution_records er
          WHERE er.realized_pnl IS NOT NULL
            AND er.created_at >= :since
            AND er.source_id = :source_id
            AND COALESCE(er.channel_id, '') = :channel_id
          GROUP BY er.user_id, er.signal_id
        )
        SELECT
          c.user_id,
          u.email AS user_email,
          COUNT(*)::int AS closed_trades,
          COUNT(*) FILTER (WHERE c.pnl > 0)::int AS wins,
          COUNT(*) FILTER (WHERE c.pnl < 0)::int AS losses,
          COUNT(*) FILTER (WHERE c.pnl = 0)::int AS breakeven,
          COALESCE(SUM(c.pnl), 0)::double precision AS total_pnl
        FROM closed c
        LEFT JOIN users u ON u.id = c.user_id
        GROUP BY c.user_id, u.email
        ORDER BY closed_trades DESC, total_pnl DESC
        """
    )
    rows = (await db.execute(sql, params)).mappings().all()
    src = (
        await db.execute(select(SignalSource).where(SignalSource.source_id == source_id))
    ).scalar_one_or_none()
    config = src.config if src and isinstance(src.config, dict) else {}
    users = []
    for r in rows:
        wins = int(r["wins"] or 0)
        losses = int(r["losses"] or 0)
        users.append(
            {
                "user_id": str(r["user_id"]),
                "user_email": r["user_email"],
                "closed_trades": int(r["closed_trades"] or 0),
                "wins": wins,
                "losses": losses,
                "breakeven": int(r["breakeven"] or 0),
                "total_pnl": round(float(r["total_pnl"] or 0), 4),
                "win_rate": _win_rate(wins, losses),
            }
        )

    return {
        "success": True,
        "data": {
            "days": days,
            "source_id": source_id,
            "source_name": src.name if src else source_id,
            "source_kind": src.kind if src else "",
            "channel_id": channel_key or None,
            "channel_label": _channel_label(config, channel_key),
            "users": users,
        },
    }
