"""Auth router — register, login, refresh, logout, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service as auth_service
from app.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.auth.utils import create_access_token, create_refresh_token
from app.database import get_db, get_redis
from app.dependencies import get_current_user
from app.models.user import User
from app.responses import success_response

router = APIRouter(prefix="/auth", tags=["Auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=dict, status_code=201)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Create the first admin account.
    Only succeeds when NO admin user exists yet (bootstrap endpoint).
    """
    user = await auth_service.register_first_admin(body.email, body.password, db)
    return success_response(UserOut.model_validate(user).model_dump())


@router.post("/login", response_model=dict)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> dict:
    """Authenticate and return access + refresh tokens."""
    user = await auth_service.authenticate_user(body.email, body.password, db)
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    await auth_service.store_refresh_token(user.id, refresh_token, redis)
    return success_response(
        TokenResponse(
            access_token=access_token, refresh_token=refresh_token
        ).model_dump()
    )


@router.post("/refresh", response_model=dict)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
) -> dict:
    """Exchange a valid refresh token for a new access token."""
    access_token = await auth_service.refresh_access_token(
        body.refresh_token, redis, db
    )
    return success_response(
        AccessTokenResponse(access_token=access_token).model_dump()
    )


@router.post("/logout", response_model=dict)
async def logout(
    body: RefreshRequest,
    redis=Depends(get_redis),
) -> dict:
    """Revoke the refresh token (add to blocklist in Redis)."""
    await auth_service.revoke_refresh_token(body.refresh_token, redis)
    return success_response({"message": "Logged out successfully"})


@router.get("/me", response_model=dict)
async def me(current_user: User = Depends(get_current_user)) -> dict:
    """Return the currently authenticated user's profile."""
    return success_response(UserOut.model_validate(current_user).model_dump())
