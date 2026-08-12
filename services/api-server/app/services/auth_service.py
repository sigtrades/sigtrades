"""认证业务：注册、Google 登录、邮箱验证。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MembershipPlan, User, UserMembership
from app.security import (
    create_access_token,
    create_refresh_token,
    generate_verification_token,
    hash_password,
    verify_password,
)
from app.services.email_service import send_verification_email, send_password_reset_email
from app.services.user_geo_service import record_user_geo_event


async def _ensure_free_membership(db: AsyncSession, user: User) -> None:
    free = await db.execute(select(MembershipPlan).where(MembershipPlan.code == "free"))
    plan = free.scalar_one_or_none()
    if plan:
        db.add(UserMembership(user_id=user.id, plan_id=plan.id, status="active"))


def _tokens(user: User) -> Tuple[str, str]:
    sub = str(user.id)
    claims = {"sub": sub, "tv": user.token_version}
    return create_access_token(claims), create_refresh_token(claims)


async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    language: str = "zh",
    *,
    send_verify_email: bool = True,
    request: Optional[Request] = None,
) -> Tuple[User, str, str, bool]:
    """返回 (user, access, refresh, verify_email_sent)。"""
    existing = await db.execute(select(User).where(User.email == email.lower()))
    if existing.scalar_one_or_none():
        raise ValueError("email already registered")

    token = generate_verification_token()
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        language=language,
        auth_provider="email",
        email_verified=False,
        email_verify_token=token,
        email_verify_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(user)
    await db.flush()
    await _ensure_free_membership(db, user)
    await db.commit()
    await db.refresh(user)

    sent = False
    if send_verify_email:
        sent = send_verification_email(user.email, token, user.language)

    if request is not None:
        await record_user_geo_event(db, user.id, request, event_type="registration", auth_method="email")

    access, refresh = _tokens(user)
    return user, access, refresh, sent


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
    request: Optional[Request] = None,
) -> Tuple[str, str]:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("invalid credentials")
    if user.auth_provider == "google" and not user.password_hash:
        raise ValueError("use google login")
    if not verify_password(password, user.password_hash):
        raise ValueError("invalid credentials")
    if not user.is_active:
        raise ValueError("account disabled")
    if request is not None:
        await record_user_geo_event(db, user.id, request, event_type="login", auth_method="email")
    return _tokens(user)


async def google_login(
    db: AsyncSession,
    email: str,
    language: str = "zh",
    *,
    request: Optional[Request] = None,
) -> Tuple[User, str, str, bool]:
    """Google 登录/自动注册。返回 (user, access, refresh, is_new_user)。"""
    email = email.lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    is_new = False
    if user is None:
        is_new = True
        user = User(
            email=email,
            password_hash="",
            language=language,
            auth_provider="google",
            email_verified=True,
        )
        db.add(user)
        await db.flush()
        await _ensure_free_membership(db, user)
        await db.commit()
        await db.refresh(user)
    elif not user.is_active:
        raise ValueError("account disabled")
    if request is not None:
        await record_user_geo_event(
            db, user.id, request,
            event_type="registration" if is_new else "login",
            auth_method="google",
        )
    access, refresh = _tokens(user)
    return user, access, refresh, is_new


async def verify_email_token(db: AsyncSession, token: str) -> User:
    """校验邮箱验证链接。幂等：同一 token 重复点击仍返回成功（避免 StrictMode/双请求误报过期）。"""
    raw = (token or "").strip()
    if not raw:
        raise ValueError("invalid or expired token")
    now = datetime.now(timezone.utc)
    result = await db.execute(select(User).where(User.email_verify_token == raw))
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("invalid or expired token")
    # 已验证：直接成功（重复打开邮件链接）
    if user.email_verified:
        return user
    expires = user.email_verify_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is None or expires <= now:
        raise ValueError("invalid or expired token")
    user.email_verified = True
    # 保留 token 至过期，便于短时间内重复请求幂等成功；重发时会轮换新 token
    await db.commit()
    await db.refresh(user)
    return user


async def resend_verification(db: AsyncSession, email: str) -> Tuple[bool, Optional[str]]:
    """返回 (sent, error_code)。error: not_found / already_verified / cooldown"""
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if not user:
        return False, "not_found"
    if user.email_verified:
        return False, "already_verified"
    if user.email_verify_expires_at:
        issued = user.email_verify_expires_at - timedelta(hours=24)
        if (datetime.now(timezone.utc) - issued).total_seconds() < 60:
            return False, "cooldown"
    token = generate_verification_token()
    user.email_verify_token = token
    user.email_verify_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    await db.commit()
    sent = send_verification_email(user.email, token, user.language)
    return sent, None


async def verify_google_credential(credential: str) -> dict:
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests

    from app.config import settings

    if not settings.GOOGLE_CLIENT_ID:
        raise ValueError("google oauth not configured")

    def _verify():
        return id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )

    return await asyncio.to_thread(_verify)


async def request_password_reset(db: AsyncSession, email: str) -> bool:
    """发送重置邮件；不存在账号也返回 True（防枚举）。"""
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if not user or user.auth_provider == "google":
        return True
    token = generate_verification_token()
    user.password_reset_token = token
    user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.commit()
    send_password_reset_email(user.email, token, user.language)
    return True


async def change_password(
    db: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    if user.auth_provider == "google":
        raise ValueError("google account cannot change password")
    if not user.password_hash or not verify_password(current_password, user.password_hash):
        raise ValueError("incorrect password")
    user.password_hash = hash_password(new_password)
    user.token_version = (user.token_version or 0) + 1
    await db.commit()


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User).where(
            User.password_reset_token == token,
            User.password_reset_expires_at > now,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise ValueError("invalid or expired token")
    user.password_hash = hash_password(new_password)
    user.password_reset_token = None
    user.password_reset_expires_at = None
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
