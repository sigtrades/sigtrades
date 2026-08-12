"""管理员 — 会员套餐 CRUD。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MembershipPlan
from app.routers.admin.deps import require_admin_only, verify_admin_token
from app.services.admin_auth import AdminContext

router = APIRouter()


class PlanUpsert(BaseModel):
    code: str
    name: str
    features: Dict[str, Any] = Field(default_factory=dict)
    stripe_price_id: Optional[str] = None
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_yearly: Optional[str] = None
    price_monthly: Optional[float] = Field(None, ge=0)
    price_yearly: Optional[float] = Field(None, ge=0)
    sort_order: int = 0
    is_active: bool = True


def _plan_dict(p: MembershipPlan) -> dict:
    return {
        "code": p.code,
        "name": p.name,
        "features": p.features,
        "stripe_price_id": p.stripe_price_id,
        "stripe_price_id_monthly": p.stripe_price_id_monthly,
        "stripe_price_id_yearly": p.stripe_price_id_yearly,
        "price_monthly": float(p.price_monthly) if p.price_monthly is not None else None,
        "price_yearly": float(p.price_yearly) if p.price_yearly is not None else None,
        "sort_order": p.sort_order,
        "is_active": bool(getattr(p, "is_active", True)),
    }


@router.get("")
async def admin_plans(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MembershipPlan).order_by(MembershipPlan.sort_order))
    plans = [_plan_dict(p) for p in result.scalars().all()]
    return {"success": True, "data": plans}


@router.put("/{code}")
async def upsert_plan(
    code: str,
    req: PlanUpsert,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MembershipPlan).where(MembershipPlan.code == code))
    plan = result.scalar_one_or_none()
    if plan is None:
        plan = MembershipPlan(code=code)
        db.add(plan)
    plan.name = req.name
    plan.features = req.features
    plan.stripe_price_id_monthly = req.stripe_price_id_monthly
    plan.stripe_price_id_yearly = req.stripe_price_id_yearly
    plan.price_monthly = req.price_monthly
    plan.price_yearly = req.price_yearly
    # 兼容旧字段：月度 Price ID 同步到 stripe_price_id
    plan.stripe_price_id = req.stripe_price_id_monthly or req.stripe_price_id
    plan.sort_order = req.sort_order
    plan.is_active = bool(req.is_active)
    await db.commit()
    return {"success": True, "data": _plan_dict(plan)}


@router.delete("/{code}")
async def delete_plan(
    code: str,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    if code == "free":
        raise HTTPException(status_code=400, detail="cannot delete free plan")
    result = await db.execute(select(MembershipPlan).where(MembershipPlan.code == code))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(plan)
    await db.commit()
    return {"success": True}
