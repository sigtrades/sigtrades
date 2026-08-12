"""管理员认证。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.routers.admin.deps import verify_admin_context
from app.services.admin_auth import AdminContext, admin_token_for_context, authenticate_admin

router = APIRouter()


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    expires_in: int
    role: str
    username: str


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(request: AdminLoginRequest):
    ctx = authenticate_admin(request.username, request.password)
    if not ctx:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return AdminLoginResponse(
        token=admin_token_for_context(ctx),
        expires_in=86400,
        role=ctx.role,
        username=ctx.username,
    )


@router.get("/me")
async def get_current_admin(ctx: AdminContext = Depends(verify_admin_context)):
    return {
        "success": True,
        "data": {
            "username": ctx.username,
            "role": ctx.role,
        },
    }
