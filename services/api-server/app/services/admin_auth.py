"""后台管理员 / 运营账号鉴权（静态 Token + 角色）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from app.config import settings

AdminRole = Literal["admin", "operations"]


@dataclass(frozen=True)
class AdminContext:
    role: AdminRole
    username: str


def resolve_admin_context(token: str) -> Optional[AdminContext]:
    raw = (token or "").strip()
    if not raw:
        return None

    if raw == settings.ADMIN_TOKEN:
        return AdminContext(role="admin", username=settings.ADMIN_USERNAME)

    if settings.OPERATIONS_TOKEN and raw == settings.OPERATIONS_TOKEN:
        return AdminContext(role="operations", username=settings.OPERATIONS_USERNAME)

    return None


def authenticate_admin(username: str, password: str) -> Optional[AdminContext]:
    u = (username or "").strip()
    p = password or ""

    if u == settings.ADMIN_USERNAME and p == settings.ADMIN_PASSWORD:
        return AdminContext(role="admin", username=settings.ADMIN_USERNAME)

    if u == settings.OPERATIONS_USERNAME and p == settings.OPERATIONS_PASSWORD:
        return AdminContext(role="operations", username=settings.OPERATIONS_USERNAME)

    return None


def admin_token_for_context(ctx: AdminContext) -> str:
    if ctx.role == "admin":
        return settings.ADMIN_TOKEN
    return settings.OPERATIONS_TOKEN
