"""Tour router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user_optional, require_admin, get_cache
from app.cache.service import CacheService
from app.models.tour import Tour
from app.models.user import User
from app.responses import list_response, success_response
from app.tours import service as tour_service
from app.tours.schemas import TourCreate, TourOut, TourPublishToggle, TourUpdate, TourDefaultToggle

router = APIRouter(prefix="/tours", tags=["Tours"])


@router.get("", response_model=dict)
async def list_tours(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
) -> dict:
    """List published tours (public endpoint)."""
    tours, total = await tour_service.list_published_tours(db, page, per_page, cache)
    return list_response(
        [t.model_dump() for t in tours],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/all", response_model=dict)
async def list_all_tours(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """List ALL tours (published + draft). Admin only."""
    from sqlalchemy import func
    from sqlalchemy.orm import selectinload
    offset = (page - 1) * per_page
    stmt = (
        select(Tour)
        .where(Tour.deleted_at.is_(None))
        .options(selectinload(Tour.scenes))
        .order_by(Tour.is_default.desc(), Tour.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    count_stmt = (
        select(func.count()).select_from(Tour).where(Tour.deleted_at.is_(None))
    )
    tours = (await db.execute(stmt)).scalars().all()
    total = (await db.execute(count_stmt)).scalar_one()
    
    def _build_tour(t: Tour) -> dict:
        data = TourOut.model_validate(t).model_dump()
        scenes = getattr(t, "scenes", [])
        data["scenes_count"] = len(scenes)
        if not data.get("cover_image_url") and scenes:
            # Fallback to the first scene's thumbnail
            data["cover_image_url"] = scenes[0].thumbnail_url or scenes[0].image_url
        return data

    return list_response(
        [_build_tour(t) for t in tours],
        total=total,
        page=page,
        per_page=per_page,
    )


def _build_single_tour(t: Tour) -> dict:
    data = TourOut.model_validate(t).model_dump()
    scenes = getattr(t, "scenes", [])
    data["scenes_count"] = len(scenes)
    if not data.get("cover_image_url") and scenes:
        data["cover_image_url"] = scenes[0].thumbnail_url or scenes[0].image_url
    return data

@router.get("/by-id/{tour_id}", response_model=dict)
async def get_tour_by_id(
    tour_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Fetch a tour by UUID (admin use). Admins can access unpublished tours."""
    tour = await tour_service._get_tour_or_404(tour_id, db)
    # Ensure scenes are loaded
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    tour = (await db.execute(select(Tour).where(Tour.id == tour_id).options(selectinload(Tour.scenes)))).scalar_one()
    return success_response(_build_single_tour(tour))

@router.get("/{slug}", response_model=dict)
async def get_tour(
    slug: str,
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_current_user_optional),
    cache: CacheService = Depends(get_cache),
) -> dict:
    tour = await tour_service.get_tour_by_slug(slug, db, viewer, cache)
    return success_response(tour.model_dump())


@router.post("", response_model=dict, status_code=201)
async def create_tour(
    body: TourCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    tour = await tour_service.create_tour(body.model_dump(), admin.id, db, cache)
    return success_response(_build_single_tour(tour))


@router.patch("/{tour_id}", response_model=dict)
async def update_tour(
    tour_id: str,
    body: TourUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    tour = await tour_service.update_tour(
        tour_id, body.model_dump(exclude_none=True), db, cache
    )
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    tour = (await db.execute(select(Tour).where(Tour.id == tour_id).options(selectinload(Tour.scenes)))).scalar_one()
    return success_response(_build_single_tour(tour))


@router.delete("/{tour_id}", response_model=dict)
async def delete_tour(
    tour_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    await tour_service.delete_tour(tour_id, db, cache)
    return success_response({"message": "Tour deleted"})


@router.patch("/{tour_id}/publish", response_model=dict)
async def publish_tour(
    tour_id: str,
    body: TourPublishToggle,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    tour = await tour_service.toggle_publish(tour_id, body.is_published, db, cache)
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    tour = (await db.execute(select(Tour).where(Tour.id == tour_id).options(selectinload(Tour.scenes)))).scalar_one()
    return success_response(_build_single_tour(tour))


@router.patch("/{tour_id}/default", response_model=dict)
async def default_tour(
    tour_id: str,
    body: TourDefaultToggle,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    tour = await tour_service.toggle_default(tour_id, body.is_default, db, cache)
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    tour = (await db.execute(select(Tour).where(Tour.id == tour_id).options(selectinload(Tour.scenes)))).scalar_one()
    return success_response(_build_single_tour(tour))
