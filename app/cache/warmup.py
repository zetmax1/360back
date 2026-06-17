import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.tour import Tour
from app.models.scene import Scene
from app.models.scene_link import SceneLink
from app.tours.schemas import TourDetailResponse, TourListItem
from app.scenes.schemas import SceneDetailResponse, SceneLinkOut
from app.cache.service import CacheService
from app.config import settings

logger = logging.getLogger(__name__)

async def warm_cache(db: AsyncSession, cache: CacheService) -> dict:
    """
    Pre-populate Redis with all published tour data.
    Call on app startup and after admin cache clear.
    Returns stats: { tours_warmed, scenes_warmed }
    """
    result = await db.execute(
        select(Tour)
        .options(
            selectinload(Tour.scenes)
            .selectinload(Scene.outgoing_links)
            .selectinload(SceneLink.to_scene)  # for to_scene_title / to_scene_image_url
        )
        .where(Tour.is_published == True, Tour.deleted_at.is_(None))
    )
    tours = result.scalars().all()

    scenes_warmed = 0
    for tour in tours:
        # Cache tour detail
        tour_response = TourDetailResponse.model_validate(tour)
        scenes_list = []
        for s in tour.scenes:
            s_data = s.__dict__.copy()
            s_data["links"] = [SceneLinkOut.from_orm_with_title(lnk) for lnk in (s.outgoing_links or [])]
            scenes_list.append(SceneDetailResponse(**s_data))
        tour_response.scenes = scenes_list
        tour_response.scenes_count = len(scenes_list)
        if not tour_response.cover_image_url and scenes_list:
            tour_response.cover_image_url = scenes_list[0].thumbnail_url or scenes_list[0].image_url

        await cache.set(
            f"tour360:tours:slug:{tour.slug}",
            tour_response.model_dump(),
            settings.CACHE_TTL_TOUR_DETAIL
        )
        # Cache each scene individually
        for scene in tour.scenes:
            s_data = scene.__dict__.copy()
            s_data["links"] = [
                SceneLinkOut.from_orm_with_title(lnk)
                for lnk in (scene.outgoing_links or [])
            ]
            scene_response = SceneDetailResponse(**s_data)
            await cache.set(
                f"tour360:scenes:{scene.id}",
                scene_response.model_dump(by_alias=True),
                settings.CACHE_TTL_SCENE
            )
            scenes_warmed += 1

    # Cache tour list
    list_response = []
    for t in tours:
        data = t.__dict__.copy()
        data["scenes_count"] = len(t.scenes)
        if not data.get("cover_image_url") and t.scenes:
            data["cover_image_url"] = t.scenes[0].thumbnail_url or t.scenes[0].image_url
        list_response.append(TourListItem(**data))

    await cache.set(
        "tour360:tours:list",
        [r.model_dump() for r in list_response],
        settings.CACHE_TTL_TOUR_LIST
    )

    logger.info(f"Cache warmup complete: {len(tours)} tours, {scenes_warmed} scenes")
    return {"tours_warmed": len(tours), "scenes_warmed": scenes_warmed}

async def warm_cache_background(db: AsyncSession, cache: CacheService):
    try:
        await warm_cache(db, cache)
    except Exception as e:
        logger.error(f"Background cache warm failed: {e}")
