"""Admin router — user management.

NOTE: Frontend API module calls these at /admin/users/* paths.
  usersApi.list()         → GET  /admin/users
  usersApi.create()       → POST /admin/users
  usersApi.toggleActive() → PATCH /admin/users/{id}/active
  usersApi.updateRole()   → PATCH /admin/users/{id}/role
  usersApi.delete()       → DELETE /admin/users/{id}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import ActiveUpdate, RoleUpdate, UserAdminOut
from app.auth.utils import hash_password
from app.database import get_db
from app.dependencies import require_admin
from app.exceptions import ConflictError, NotFoundError
from app.models.user import User, UserRole
from app.responses import list_response, success_response

router = APIRouter(prefix="/admin", tags=["Admin"])


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole = UserRole.viewer

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


@router.get("/users", response_model=dict)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    offset = (page - 1) * per_page
    users = (
        await db.execute(
            select(User).order_by(User.created_at.desc()).offset(offset).limit(per_page)
        )
    ).scalars().all()
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    return list_response(
        [UserAdminOut.model_validate(u).model_dump() for u in users],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/users", response_model=dict, status_code=201)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Create a new user (admin can create other admins or viewers)."""
    existing = (
        await db.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    await db.flush()
    return success_response(UserAdminOut.model_validate(user).model_dump())


@router.patch("/users/{user_id}/role", response_model=dict)
async def change_user_role(
    user_id: str,
    body: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User '{user_id}' not found")
    user.role = body.role
    await db.flush()
    return success_response(UserAdminOut.model_validate(user).model_dump())


@router.patch("/users/{user_id}/active", response_model=dict)
async def toggle_user_active(
    user_id: str,
    body: ActiveUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> dict:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User '{user_id}' not found")
    # Prevent admin from deactivating themselves
    if user_id == current_admin.id and not body.is_active:
        raise ConflictError("You cannot deactivate your own account")
    user.is_active = body.is_active
    await db.flush()
    return success_response(UserAdminOut.model_validate(user).model_dump())


@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> dict:
    # Prevent admin from deleting themselves
    if user_id == current_admin.id:
        raise ConflictError("You cannot delete your own account")
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError(f"User '{user_id}' not found")
    await db.delete(user)
    await db.flush()
    return success_response({"message": "User deleted"})
