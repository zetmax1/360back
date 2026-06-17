"""Auth business logic — all DB/Redis operations live here."""
from __future__ import annotations

import logging

import redis.asyncio as aioredis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.utils import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.config import settings
from app.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# Redis key for refresh-token blocklist
_BLOCKLIST_PREFIX = "rt_blocklist:"
_REFRESH_KEY_PREFIX = "refresh_token:"


async def register_first_admin(
    email: str, password: str, db: AsyncSession
) -> User:
    """
    Create the very first admin account.
    Raises ConflictError if any admin already exists.
    """
    stmt = select(func.count()).select_from(User).where(User.role == UserRole.admin)
    count = (await db.execute(stmt)).scalar_one()
    if count > 0:
        raise ConflictError(
            "An admin account already exists. Contact your administrator."
        )

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ConflictError("Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(password),
        role=UserRole.admin,
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate_user(
    email: str, password: str, db: AsyncSession
) -> User:
    """Verify credentials and return the user object."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise ForbiddenError("Account is disabled")

    return user


async def store_refresh_token(
    user_id: str, refresh_token: str, redis: aioredis.Redis
) -> None:
    """Persist refresh token in Redis with TTL."""
    key = f"{_REFRESH_KEY_PREFIX}{refresh_token}"
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86_400
    await redis.set(key, user_id, ex=ttl)


async def revoke_refresh_token(refresh_token: str, redis: aioredis.Redis) -> None:
    """Move refresh token to blocklist (logout)."""
    key = f"{_REFRESH_KEY_PREFIX}{refresh_token}"
    user_id = await redis.get(key)
    if user_id:
        await redis.delete(key)
        blocklist_key = f"{_BLOCKLIST_PREFIX}{refresh_token}"
        await redis.set(
            blocklist_key,
            "revoked",
            ex=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86_400,
        )


async def refresh_access_token(
    refresh_token: str, redis: aioredis.Redis, db: AsyncSession
) -> str:
    """Validate refresh token and issue a new access token."""
    # Check blocklist first
    blocklist_key = f"{_BLOCKLIST_PREFIX}{refresh_token}"
    if await redis.get(blocklist_key):
        raise UnauthorizedError("Refresh token has been revoked")

    user_id = decode_token(refresh_token, expected_type="refresh")

    # Verify token is still in Redis (hasn't been cleaned up)
    stored_key = f"{_REFRESH_KEY_PREFIX}{refresh_token}"
    stored_uid = await redis.get(stored_key)
    if not stored_uid or stored_uid != user_id:
        raise UnauthorizedError("Refresh token is invalid or expired")

    # Validate user still exists and is active
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("User no longer active")

    return create_access_token(user_id)


async def get_user_by_id(user_id: str, db: AsyncSession) -> User:
    user = await db.get(User, user_id)
    if not user:
        raise UnauthorizedError("User not found")
    return user
