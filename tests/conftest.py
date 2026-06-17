"""
Test configuration and shared fixtures.

Uses an in-process async SQLite database so no external PostgreSQL is needed.
Override ENVIRONMENT vars before importing app to use test settings.
"""
from __future__ import annotations

import os
import pytest
import pytest_asyncio

# Override settings BEFORE importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("SECRET_KEY", "test_secret_key_that_is_at_least_32_chars_long")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("UPLOAD_DIR", "/tmp/tour360_test_uploads")

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.database import get_db
from app.models.base import Base
from app.auth.utils import hash_password, create_access_token
from app.models.user import User, UserRole
from app.models.tour import Tour
from app.models.scene import Scene

# ── Test database engine ──────────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def create_tables():
    """Create all tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()

@pytest_asyncio.fixture(scope="function", autouse=True)
async def clear_redis():
    """Clear Redis before each test to prevent state leakage."""
    import redis.asyncio as aioredis
    from app.config import settings
    from app.auth.router import limiter
    from app.database import close_redis
    r = aioredis.from_url(settings.REDIS_URL)
    await r.flushdb()
    await r.aclose()
    limiter.reset()
    await close_redis()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Provide a test DB session that rolls back after each test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db: AsyncSession):
    """AsyncClient with DB dependency overridden to use the test session."""

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Shared user fixtures ──────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        email="admin@example.com",
        hashed_password=hash_password("adminpass123"),
        role=UserRole.admin,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def viewer_user(db: AsyncSession) -> User:
    user = User(
        email="viewer@example.com",
        hashed_password=hash_password("viewerpass123"),
        role=UserRole.viewer,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
def admin_token(admin_user: User) -> str:
    return create_access_token(admin_user.id)


@pytest_asyncio.fixture
def viewer_token(viewer_user: User) -> str:
    return create_access_token(viewer_user.id)


@pytest_asyncio.fixture
def admin_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
def viewer_headers(viewer_token: str) -> dict:
    return {"Authorization": f"Bearer {viewer_token}"}


# ── Shared entity fixtures ────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def published_tour(db: AsyncSession, admin_user: User) -> Tour:
    tour = Tour(
        slug="test-tour",
        title="Test Tour",
        is_published=True,
        created_by=admin_user.id,
    )
    db.add(tour)
    await db.flush()
    return tour


@pytest_asyncio.fixture
async def unpublished_tour(db: AsyncSession, admin_user: User) -> Tour:
    tour = Tour(
        slug="draft-tour",
        title="Draft Tour",
        is_published=False,
        created_by=admin_user.id,
    )
    db.add(tour)
    await db.flush()
    return tour


@pytest_asyncio.fixture
async def scene_a(db: AsyncSession, published_tour: Tour) -> Scene:
    scene = Scene(
        tour_id=published_tour.id,
        title="Scene A",
        image_url="http://testserver/uploads/a.jpg",
        order_index=0,
    )
    db.add(scene)
    await db.flush()
    return scene


@pytest_asyncio.fixture
async def scene_b(db: AsyncSession, published_tour: Tour) -> Scene:
    scene = Scene(
        tour_id=published_tour.id,
        title="Scene B",
        image_url="http://testserver/uploads/b.jpg",
        order_index=1,
    )
    db.add(scene)
    await db.flush()
    return scene
