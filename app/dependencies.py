"""
Shared FastAPI dependencies.

Usage in routers:
    async def my_endpoint(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        admin: User = Depends(require_admin),
    ): ...
"""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.service import get_user_by_id
from app.auth.utils import decode_token
from app.database import get_db, get_redis
from app.exceptions import ForbiddenError, UnauthorizedError
from app.models.user import User, UserRole
from sqlalchemy.ext.asyncio import AsyncSession
from app.cache.service import CacheService

_bearer = HTTPBearer(auto_error=False)

async def get_cache(redis: aioredis.Redis = Depends(get_redis)) -> CacheService:
    return CacheService(redis)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the Bearer token → return authenticated User."""
    if not credentials:
        raise UnauthorizedError("Authentication required")

    user_id = decode_token(credentials.credentials, expected_type="access")
    user = await get_user_by_id(user_id, db)

    if not user.is_active:
        raise ForbiddenError("Account is disabled")

    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Like get_current_user but returns None for unauthenticated requests."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials, db)
    except Exception:
        return None


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Guard: current user must have admin role."""
    if current_user.role != UserRole.admin:
        raise ForbiddenError("Admin access required")
    return current_user


def require_role(*roles: UserRole):
    """Factory dependency: require one of the given roles."""

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise ForbiddenError(
                f"Required role(s): {', '.join(r.value for r in roles)}"
            )
        return current_user

    return _check
