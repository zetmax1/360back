"""Tour business logic."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import ConflictError, NotFoundError, TourNotPublishedError
from app.models.scene import Scene
from app.models.scene_link import SceneLink
from app.models.tour import Tour
from app.models.user import User, UserRole
from app.cache.service import CacheService
from app.config import settings
from app.tours.schemas import TourDetailResponse, TourListItem

async def _get_tour_or_404(tour_id: str, db: AsyncSession) -> Tour:
    tour = await db.get(Tour, tour_id)
    if not tour or tour.deleted_at is not None:
        raise NotFoundError(f"Tour with id '{tour_id}' does not exist", code="NOT_FOUND")
    return tour


async def list_published_tours(
    db: AsyncSession, page: int = 1, per_page: int = 20, cache: CacheService = None
) -> tuple[list[TourListItem], int]:
    offset = (page - 1) * per_page
    
    if cache and page == 1:
        cached = await cache.get("tour360:tours:list")
        if cached:
            return [TourListItem(**t) for t in cached], len(cached)
            
    stmt = (
        select(Tour)
        .where(Tour.is_published.is_(True), Tour.deleted_at.is_(None))
        .options(selectinload(Tour.scenes))
        .order_by(Tour.is_default.desc(), Tour.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    count_stmt = (
        select(func.count())
        .select_from(Tour)
        .where(Tour.is_published.is_(True), Tour.deleted_at.is_(None))
    )
    tours = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()
    
    items = []
    for t in tours:
        data = t.__dict__.copy()
        data["scenes_count"] = len(t.scenes)
        if not data.get("cover_image_url") and t.scenes:
            data["cover_image_url"] = t.scenes[0].thumbnail_url or t.scenes[0].image_url
        # Find entry scene (or first scene) for hero panorama
        entry_scene = next((s for s in t.scenes if s.is_entry_point), None) or (t.scenes[0] if t.scenes else None)
        if entry_scene:
            data["entry_scene_image_url"] = entry_scene.image_url
            data["entry_scene_thumbnail_url"] = entry_scene.thumbnail_url
        items.append(TourListItem(**data))
        
    if cache and page == 1:
        await cache.set("tour360:tours:list", [i.model_dump() for i in items], settings.CACHE_TTL_TOUR_LIST)
        
    return items, total


async def get_tour_by_slug(
    slug: str,
    db: AsyncSession,
    viewer: User | None = None,
    cache: CacheService = None
) -> TourDetailResponse:
    cache_key = f"tour360:tours:slug:{slug}"
    
    if cache and (not viewer or viewer.role != UserRole.admin):
        cached = await cache.get(cache_key)
        if cached:
            return TourDetailResponse(**cached)

    stmt = (
        select(Tour)
        .where(Tour.slug == slug, Tour.deleted_at.is_(None))
        .options(
            selectinload(Tour.scenes).selectinload(Scene.outgoing_links)
            .selectinload(SceneLink.to_scene)
        )
    )
    tour = (await db.execute(stmt)).scalar_one_or_none()
    if not tour:
        raise NotFoundError(f"Tour '{slug}' not found")

    is_admin = viewer and viewer.role == UserRole.admin
    if not tour.is_published and not is_admin:
        raise TourNotPublishedError(
            "This tour is not yet published",
        )
        
    response = TourDetailResponse.model_validate(tour)
    from app.scenes.schemas import SceneDetailResponse, SceneLinkOut
    scenes_list = []
    for s in tour.scenes:
        s_data = s.__dict__.copy()
        s_data["links"] = [SceneLinkOut.from_orm_with_title(lnk) for lnk in (s.outgoing_links or [])]
        scenes_list.append(SceneDetailResponse(**s_data))
    response.scenes = scenes_list
    response.scenes_count = len(scenes_list)
    if not response.cover_image_url and scenes_list:
        response.cover_image_url = scenes_list[0].thumbnail_url or scenes_list[0].image_url

    if cache and tour.is_published:
        await cache.set(cache_key, response.model_dump(), settings.CACHE_TTL_TOUR_DETAIL)

    return response


async def create_tour(data: dict, creator_id: str, db: AsyncSession, cache: CacheService = None) -> Tour:
    from sqlalchemy import update
    # Slug uniqueness check
    existing = (
        await db.execute(select(Tour).where(Tour.slug == data["slug"]))
    ).scalar_one_or_none()
    if existing:
        raise ConflictError(
            f"A tour with slug '{data['slug']}' already exists",
            code="CONFLICT",
        )
    
    if data.get("is_default"):
        await db.execute(update(Tour).values(is_default=False))
        
    tour = Tour(**data, created_by=creator_id)
    db.add(tour)
    await db.commit()
    if cache:
        await cache.invalidate_tour(str(tour.id), tour.slug)
    return tour


async def update_tour(tour_id: str, data: dict, db: AsyncSession, cache: CacheService = None) -> Tour:
    from sqlalchemy import update
    tour = await _get_tour_or_404(tour_id, db)
    
    if data.get("is_default") is True:
        await db.execute(update(Tour).where(Tour.id != tour_id).values(is_default=False))
        
    for key, value in data.items():
        if value is not None:
            setattr(tour, key, value)
    await db.commit()
    if cache:
        await cache.invalidate_tour(str(tour.id), tour.slug)
    return tour


async def delete_tour(tour_id: str, db: AsyncSession, cache: CacheService = None) -> None:
    """Soft delete."""
    tour = await _get_tour_or_404(tour_id, db)
    tour.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    if cache:
        await cache.invalidate_tour(str(tour.id), tour.slug)


async def toggle_publish(tour_id: str, is_published: bool, db: AsyncSession, cache: CacheService = None) -> Tour:
    tour = await _get_tour_or_404(tour_id, db)
    tour.is_published = is_published
    await db.commit()
    if cache:
        await cache.invalidate_tour(str(tour.id), tour.slug)
    return tour


async def toggle_default(tour_id: str, is_default: bool, db: AsyncSession, cache: CacheService = None) -> Tour:
    from sqlalchemy import update
    tour = await _get_tour_or_404(tour_id, db)
    tour.is_default = is_default
    if is_default:
        await db.execute(update(Tour).where(Tour.id != tour_id).values(is_default=False))
    await db.commit()
    if cache:
        await cache.invalidate_tour(str(tour.id), tour.slug)
    return tour

