"""SceneLink business logic."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.exceptions import (
    DuplicateLinkError,
    InvalidDegreeError,
    NotFoundError,
    SelfLinkError,
    CrossTourLinkError,
)
from app.models.scene import Scene
from app.models.tour import Tour
from app.models.scene_link import SceneLink
from app.cache.service import CacheService


async def _get_scene_or_404(scene_id: str, db: AsyncSession) -> Scene:
    scene = await db.get(Scene, scene_id)
    if not scene:
        raise NotFoundError(f"Scene '{scene_id}' not found")
    return scene


async def _get_link_or_404(link_id: str, db: AsyncSession) -> SceneLink:
    """Fetch link with to_scene eagerly loaded (for to_scene_title)."""
    stmt = (
        select(SceneLink)
        .where(SceneLink.id == link_id)
        .options(selectinload(SceneLink.to_scene))
    )
    link = (await db.execute(stmt)).scalar_one_or_none()
    if not link:
        raise NotFoundError(f"Link '{link_id}' not found")
    return link


async def list_links(scene_id: str, db: AsyncSession) -> list[SceneLink]:
    await _get_scene_or_404(scene_id, db)
    result = await db.execute(
        select(SceneLink)
        .where(SceneLink.from_scene_id == scene_id)
        .options(selectinload(SceneLink.to_scene))  # for to_scene_title
    )
    return list(result.scalars().all())


async def create_link(
    from_scene_id: str, data: dict, db: AsyncSession, cache: CacheService = None
) -> SceneLink:
    to_scene_id: str = data["to_scene_id"]
    degree: float = data["degree"]

    # Application-level guard before hitting DB constraints
    if from_scene_id == to_scene_id:
        raise SelfLinkError("A scene cannot link to itself")

    if not (0.0 <= degree < 360.0):
        raise InvalidDegreeError(
            f"degree {degree} is outside valid range [0, 360)", field="degree"
        )

    from_scene = await _get_scene_or_404(from_scene_id, db)
    to_scene = await _get_scene_or_404(to_scene_id, db)

    if from_scene.tour_id != to_scene.tour_id:
        raise CrossTourLinkError("Cannot link scenes from different tours")

    # Duplicate check
    existing = (
        await db.execute(
            select(SceneLink).where(
                SceneLink.from_scene_id == from_scene_id,
                SceneLink.to_scene_id == to_scene_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise DuplicateLinkError(
            f"A link from scene '{from_scene_id}' to '{to_scene_id}' already exists"
        )

    link = SceneLink(from_scene_id=from_scene_id, **data)
    db.add(link)
    
    # Auto-create reverse link if it doesn't exist
    reverse_existing = (
        await db.execute(
            select(SceneLink).where(
                SceneLink.from_scene_id == to_scene_id,
                SceneLink.to_scene_id == from_scene_id,
            )
        )
    ).scalar_one_or_none()
    
    if not reverse_existing:
        reverse_degree = (degree + 180.0) % 360.0
        reverse_link = SceneLink(
            from_scene_id=to_scene_id,
            to_scene_id=from_scene_id,
            degree=reverse_degree,
            label=f"Back to {from_scene.title}"
        )
        db.add(reverse_link)

    await db.commit()
    if cache:
        tour = await _get_scene_or_404(from_scene_id, db) # get scene to find tour
        tour_model = await db.get(Tour, tour.tour_id)
        await cache.invalidate_scene(from_scene_id, tour.tour_id, tour_model.slug)
        await cache.invalidate_scene(to_scene_id, tour.tour_id, tour_model.slug)
    # Reload with to_scene for to_scene_title resolution in response
    return await _get_link_or_404(link.id, db)


async def update_link(link_id: str, data: dict, db: AsyncSession, cache: CacheService = None) -> SceneLink:
    link = await _get_link_or_404(link_id, db)
    if "degree" in data and data["degree"] is not None:
        degree = data["degree"]
        if not (0.0 <= degree < 360.0):
            raise InvalidDegreeError(
                f"degree {degree} is outside valid range [0, 360)", field="degree"
            )
    for key, value in data.items():
        if value is not None:
            setattr(link, key, value)
    await db.commit()
    if cache:
        tour = await _get_scene_or_404(link.from_scene_id, db)
        tour_model = await db.get(Tour, tour.tour_id)
        await cache.invalidate_scene(link.from_scene_id, tour.tour_id, tour_model.slug)
        await cache.invalidate_scene(link.to_scene_id, tour.tour_id, tour_model.slug)
    return link


async def delete_link(link_id: str, db: AsyncSession, cache: CacheService = None) -> None:
    link = await _get_link_or_404(link_id, db)
    from_scene_id = link.from_scene_id
    to_scene_id = link.to_scene_id
    await db.delete(link)
    await db.commit()
    if cache:
        tour = await _get_scene_or_404(from_scene_id, db)
        tour_model = await db.get(Tour, tour.tour_id)
        await cache.invalidate_scene(from_scene_id, tour.tour_id, tour_model.slug)
        await cache.invalidate_scene(to_scene_id, tour.tour_id, tour_model.slug)
