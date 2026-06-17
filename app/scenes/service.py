"""Scene business logic."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ForbiddenError, NotFoundError, TourNotPublishedError
from app.models.scene import Scene
from app.models.scene_link import SceneLink
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.cache.service import CacheService
from app.config import settings
from app.scenes.schemas import SceneDetailResponse, SceneLinkOut, SceneOut

async def _get_tour_or_404(tour_id: str, db: AsyncSession) -> Tour:
    tour = await db.get(Tour, tour_id)
    if not tour or tour.deleted_at is not None:
        raise NotFoundError(f"Tour '{tour_id}' not found")
    return tour

async def _get_scene_or_404(scene_id: str, db: AsyncSession) -> Scene:
    scene = await db.get(Scene, scene_id)
    if not scene:
        raise NotFoundError(f"Scene '{scene_id}' not found")
    return scene

async def list_scenes(
    tour_id: str,
    db: AsyncSession,
    viewer: User | None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[Scene], int]:
    tour = await _get_tour_or_404(tour_id, db)
    is_admin = viewer and viewer.role == UserRole.admin
    if not tour.is_published and not is_admin:
        raise TourNotPublishedError("Tour is not published")

    offset = (page - 1) * per_page
    stmt = (
        select(Scene)
        .where(Scene.tour_id == tour_id)
        .options(
            selectinload(Scene.outgoing_links).selectinload(SceneLink.to_scene)
        )
        .order_by(Scene.order_index.asc())
        .offset(offset)
        .limit(per_page)
    )
    count_stmt = select(func.count()).select_from(Scene).where(Scene.tour_id == tour_id)
    scenes = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()
    return list(scenes), total

async def get_scene(scene_id: str, db: AsyncSession, cache: CacheService = None) -> dict:
    cache_key = f"tour360:scenes:{scene_id}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return cached

    stmt = (
        select(Scene)
        .where(Scene.id == scene_id)
        .options(
            selectinload(Scene.outgoing_links).selectinload(SceneLink.to_scene)
        )
    )
    scene = (await db.execute(stmt)).scalar_one_or_none()

    if not scene:
        raise NotFoundError(f"Scene '{scene_id}' not found")

    s_data = SceneOut.model_validate(scene).model_dump(by_alias=True)

    s_data["links"] = [
        SceneLinkOut.from_orm_with_title(lnk).model_dump()
        for lnk in (scene.outgoing_links or [])
    ]
    
    if cache:
        await cache.set(cache_key, s_data, settings.CACHE_TTL_SCENE)
        
    return s_data

async def create_scene(tour_id: str, data: dict, db: AsyncSession, cache: CacheService = None) -> Scene:
    await _get_tour_or_404(tour_id, db)
    scene = Scene(tour_id=tour_id, **data)
    # If this is marked as entry point, unset others in the tour
    if data.get("is_entry_point"):
        await _clear_entry_point(tour_id, db)
    db.add(scene)
    await db.commit()
    if cache:
        tour = await _get_tour_or_404(tour_id, db)
        await cache.invalidate_scene(str(scene.id), tour_id, tour.slug)
    return scene

async def update_scene(scene_id: str, data: dict, db: AsyncSession, cache: CacheService = None) -> dict:
    scene = await _get_scene_or_404(scene_id, db)
    for key, value in data.items():
        setattr(scene, key, value)
    await db.commit()
    if cache:
        tour = await _get_tour_or_404(scene.tour_id, db)
        await cache.invalidate_scene(str(scene.id), scene.tour_id, tour.slug)
    # Reload with links for response building
    return await get_scene(scene_id, db, cache)

async def delete_scene(scene_id: str, db: AsyncSession, cache: CacheService = None) -> None:
    scene = await _get_scene_or_404(scene_id, db)
    tour_id = scene.tour_id
    await db.delete(scene)
    await db.commit()
    if cache:
        tour = await _get_tour_or_404(tour_id, db)
        await cache.invalidate_scene(scene_id, tour_id, tour.slug)

async def set_entry_point(scene_id: str, db: AsyncSession, cache: CacheService = None) -> dict:
    scene = await _get_scene_or_404(scene_id, db)
    await _clear_entry_point(scene.tour_id, db)
    scene.is_entry_point = True
    await db.commit()
    if cache:
        tour = await _get_tour_or_404(scene.tour_id, db)
        await cache.invalidate_scene(scene_id, scene.tour_id, tour.slug)
    # Reload with links for response building
    return await get_scene(scene_id, db, cache)

async def _clear_entry_point(tour_id: str, db: AsyncSession) -> None:
    """Remove entry_point flag from all scenes in the tour."""
    scenes = (
        await db.execute(
            select(Scene).where(Scene.tour_id == tour_id, Scene.is_entry_point.is_(True))
        )
    ).scalars().all()
    for s in scenes:
        s.is_entry_point = False
    await db.flush()
