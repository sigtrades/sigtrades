from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User
from app.security import decode_token

bearer = HTTPBearer(auto_error=False)


def require_internal(x_internal_secret: Optional[str] = Header(default=None)) -> None:
    if x_internal_secret != settings.INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="invalid internal secret")


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    payload = decode_token(creds.credentials, "access")
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="invalid token")
    try:
        uid = uuid.UUID(payload["sub"])
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid token subject")
    result = await db.execute(select(User).where(User.id == uid, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    tv = payload.get("tv", 0)
    if tv != user.token_version:
        raise HTTPException(status_code=401, detail="token revoked")
    return user


async def get_verified_user(user: User = Depends(get_current_user)) -> User:
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.email_verified:
        raise HTTPException(status_code=403, detail="email_not_verified")
    return user
