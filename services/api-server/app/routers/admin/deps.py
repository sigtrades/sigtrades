"""Admin API dependencies."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.admin_auth import AdminContext, resolve_admin_context

security = HTTPBearer(auto_error=False)


def _extract_admin_token(
    credentials: HTTPAuthorizationCredentials | None,
    x_admin_token: str | None,
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    if x_admin_token:
        return x_admin_token
    return None


async def verify_admin_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    x_admin_token: str = Header(None, alias="X-Admin-Token"),
) -> AdminContext:
    """验证管理员 / 运营 Token，并返回角色上下文。"""
    token = _extract_admin_token(credentials, x_admin_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供管理员凭证",
        )

    ctx = resolve_admin_context(token)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员凭证无效",
        )
    return ctx


async def require_admin_only(
    ctx: AdminContext = Depends(verify_admin_context),
) -> AdminContext:
    """仅超级管理员可访问（运营账号禁止写操作）。"""
    if ctx.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号无此操作权限",
        )
    return ctx


async def verify_admin_token(
    ctx: AdminContext = Depends(verify_admin_context),
) -> bool:
    """兼容旧依赖签名（Bearer 或 X-Admin-Token）。"""
    return True
