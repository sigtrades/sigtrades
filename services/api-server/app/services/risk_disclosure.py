"""风险揭示书：当前版本、正文加载、同意状态查询与写入。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RiskDisclosureAgreement
from app.utils.datetime import format_et

# 文档版本：内容重大变更时递增，未同意新版本的用户需重新确认
RISK_DISCLOSURE_VERSION = "2026-07-31"

_DOC_CANDIDATES = (
    Path("/app/data/legal/risk_disclosure_zh.md"),
    Path(__file__).resolve().parents[2] / "data" / "legal" / "risk_disclosure_zh.md",
)


def load_risk_disclosure_markdown() -> str:
    for path in _DOC_CANDIDATES:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("risk_disclosure_zh.md not found")


async def user_has_agreed(
    db: AsyncSession, user_id: uuid.UUID, version: str = RISK_DISCLOSURE_VERSION
) -> bool:
    row = (
        await db.execute(
            select(RiskDisclosureAgreement.id).where(
                RiskDisclosureAgreement.user_id == user_id,
                RiskDisclosureAgreement.version == version,
            ).limit(1)
        )
    ).scalar_one_or_none()
    return row is not None


async def latest_agreement(
    db: AsyncSession, user_id: uuid.UUID, version: str = RISK_DISCLOSURE_VERSION
) -> Optional[RiskDisclosureAgreement]:
    return (
        await db.execute(
            select(RiskDisclosureAgreement)
            .where(
                RiskDisclosureAgreement.user_id == user_id,
                RiskDisclosureAgreement.version == version,
            )
            .order_by(RiskDisclosureAgreement.agreed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def record_agreement(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    version: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> RiskDisclosureAgreement:
    if version != RISK_DISCLOSURE_VERSION:
        raise ValueError("risk disclosure version mismatch")
    existing = await latest_agreement(db, user_id, version)
    if existing:
        return existing
    row = RiskDisclosureAgreement(
        user_id=user_id,
        version=version,
        ip_address=(ip_address or "")[:64] or None,
        user_agent=(user_agent or "")[:512] or None,
        meta=meta or {},
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_user_agreements(db: AsyncSession, user_id: uuid.UUID) -> List[Dict[str, Any]]:
    rows = (
        await db.execute(
            select(RiskDisclosureAgreement)
            .where(RiskDisclosureAgreement.user_id == user_id)
            .order_by(RiskDisclosureAgreement.agreed_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "version": r.version,
            "agreed_at": format_et(r.agreed_at),
            "ip_address": r.ip_address,
            "user_agent": r.user_agent,
            "meta": r.meta or {},
        }
        for r in rows
    ]
