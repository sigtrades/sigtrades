"""Admin API — 聚合子路由。"""

from __future__ import annotations

from fastapi import APIRouter

from app.routers.admin import (
    agents,
    analytics,
    auth,
    executions,
    inbound_mail,
    in_app_broadcasts,
    membership,
    payments,
    promotions,
    settings,
    sources,
    subscriptions,
    users,
)
from app.routers.admin.agents import admin_agent_presence_alias
from app.routers.admin.agent_releases import router as agent_releases_router
from app.routers.admin.sources import discord_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(auth.router, tags=["admin-auth"])
router.include_router(users.router, prefix="/users", tags=["admin-users"])
router.include_router(analytics.router, prefix="/analytics", tags=["admin-analytics"])
router.include_router(membership.router, prefix="/membership-plans", tags=["admin-membership"])
router.include_router(sources.router, prefix="/signal-sources", tags=["admin-sources"])
router.include_router(discord_router, prefix="/discord", tags=["admin-discord"])
router.include_router(subscriptions.router, prefix="/subscriptions", tags=["admin-subscriptions"])
router.include_router(agents.router, prefix="/agents", tags=["admin-agents"])
router.include_router(agent_releases_router, prefix="/agents", tags=["admin-agents"])
router.add_api_route(
    "/agent-presence",
    admin_agent_presence_alias,
    methods=["GET"],
    tags=["admin-agents"],
)
router.include_router(executions.router, prefix="/executions", tags=["admin-executions"])
router.include_router(inbound_mail.router, prefix="/inbound-mails", tags=["admin-inbound-mail"])
router.include_router(payments.router, prefix="/payments", tags=["admin-payments"])
router.include_router(promotions.router, prefix="/promotions", tags=["admin-promotions"])
router.include_router(in_app_broadcasts.router, prefix="/in-app-broadcasts", tags=["admin-broadcasts"])
router.include_router(settings.router, prefix="/settings", tags=["admin-settings"])
