from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user
from app.database import get_db
from app.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    GoogleLoginRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailResponse,
)
from app.security import decode_token
from app.services import auth_service
from app.services.rate_limit import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", dependencies=[Depends(rate_limit("register", limit=5, window=3600))])
async def register(req: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        user, access, refresh, verify_sent = await auth_service.register_user(
            db, req.email, req.password, req.language, request=request
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "email_verified": user.email_verified,
        "verify_email_sent": verify_sent,
    }


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("login", limit=10, window=300))],
)
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        access, refresh = await auth_service.login_user(db, req.email, req.password, request=request)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("refresh", limit=30, window=300))],
)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token, "refresh")
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    sub = payload["sub"]

    # 校验用户存在且启用：禁用/删除用户的旧 refresh token 不再续签。
    import uuid as _uuid

    from sqlalchemy import select as _select

    from app.models import User

    try:
        uid = _uuid.UUID(sub)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="invalid refresh token")
    user = (await db.execute(_select(User).where(User.id == uid))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="user inactive")
    tv = payload.get("tv", 0)
    if tv != user.token_version:
        raise HTTPException(status_code=401, detail="token revoked")

    from app.services.auth_service import _tokens

    access, refresh_tok = _tokens(user)
    return TokenResponse(access_token=access, refresh_token=refresh_tok)


@router.post("/google", dependencies=[Depends(rate_limit("google", limit=20, window=300))])
async def google_login(req: GoogleLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        idinfo = await auth_service.verify_google_credential(req.credential)
    except ValueError as e:
        raise HTTPException(status_code=503 if "not configured" in str(e) else 401, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"invalid google token: {e}")

    email = idinfo.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="email missing from google")
    if not idinfo.get("email_verified"):
        raise HTTPException(status_code=400, detail="google email not verified")

    try:
        user, access, refresh, is_new = await auth_service.google_login(
            db, email, req.language, request=request
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "email_verified": user.email_verified,
        "is_new_user": is_new,
    }


@router.get("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    try:
        user = await auth_service.verify_email_token(db, token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return VerifyEmailResponse(ok=True, email=user.email)


@router.post(
    "/resend-verification",
    dependencies=[Depends(rate_limit("resend_verification", limit=5, window=3600))],
)
async def resend_verification(req: ResendVerificationRequest, db: AsyncSession = Depends(get_db)):
    sent, err = await auth_service.resend_verification(db, req.email)
    if err == "not_found":
        return {"ok": True, "message": "if account exists, email sent"}
    if err == "already_verified":
        raise HTTPException(status_code=400, detail="already verified")
    if err == "cooldown":
        raise HTTPException(status_code=429, detail="please wait before resending")
    return {"ok": sent}


@router.post(
    "/forgot-password",
    dependencies=[Depends(rate_limit("forgot_password", limit=5, window=3600))],
)
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.request_password_reset(db, req.email)
    return {"ok": True, "message": "if account exists, reset email sent"}


@router.post(
    "/reset-password",
    dependencies=[Depends(rate_limit("reset_password", limit=10, window=3600))],
)
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    try:
        await auth_service.reset_password(db, req.token, req.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post(
    "/change-password",
    dependencies=[Depends(rate_limit("change_password", limit=10, window=3600))],
)
async def change_password(
    req: ChangePasswordRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import User as UserModel

    if not isinstance(user, UserModel):
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        await auth_service.change_password(db, user, req.current_password, req.new_password)
    except ValueError as e:
        msg = str(e)
        if msg == "incorrect password":
            raise HTTPException(status_code=400, detail=msg)
        if msg == "google account cannot change password":
            raise HTTPException(status_code=400, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True}
