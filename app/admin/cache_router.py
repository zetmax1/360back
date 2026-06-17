from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.dependencies import require_admin, get_db
from app.cache.service import CacheService
from app.dependencies import get_cache
from app.tours import service as tour_service
from app.cache.warmup import warm_cache_background

router = APIRouter(prefix="/admin", tags=["Admin", "Cache"])

@router.get("/cache/stats")
async def get_cache_stats(
    cache: CacheService = Depends(get_cache),
    admin: User = Depends(require_admin),
):
    """Returns Redis cache statistics for the admin dashboard."""
    stats = await cache.stats()
    return {"data": stats}

@router.post("/cache/clear")
async def clear_all_cache(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
    admin: User = Depends(require_admin),
):
    """
    Nuclear cache clear — deletes all tour360:* keys from Redis.
    Immediately triggers cache warmup in background.
    Admin only.
    """
    deleted_count = await cache.invalidate_all()

    # Re-warm cache in background so next user request is still fast
    background_tasks.add_task(warm_cache_background, db, cache)

    return {
        "data": {
            "deleted_keys": deleted_count,
            "warming": True,
            "message": f"Cleared {deleted_count} cache keys. Re-warming in background."
        }
    }

@router.post("/cache/clear/tour/{tour_id}")
async def clear_tour_cache(
    tour_id: str,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
    admin: User = Depends(require_admin),
):
    """Clear cache for a specific tour only — less aggressive than full clear."""
    tour = await tour_service._get_tour_or_404(tour_id, db)
    await cache.invalidate_tour(tour_id, tour.slug)
    
    # Also invalidate individual scene caches for this tour
    from sqlalchemy import select
    from app.models.scene import Scene
    scenes = await db.execute(select(Scene.id).where(Scene.tour_id == tour_id))
    for scene_id in scenes.scalars().all():
        await cache.delete(f"tour360:scenes:{scene_id}")
        await cache.delete(f"tour360:scenes:{scene_id}:links")
        
    return {"data": {"message": f"Cache cleared for tour: {tour.title}"}}

@router.post("/cache/warm")
async def trigger_warmup(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
    admin: User = Depends(require_admin),
):
    """Manually trigger cache warmup without clearing first."""
    background_tasks.add_task(warm_cache_background, db, cache)
    return {"data": {"message": "Cache warmup started in background"}}
