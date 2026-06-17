"""Scenes router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user_optional, require_admin, get_cache
from app.cache.service import CacheService
from app.models.scene import Scene
from app.models.user import User
from app.responses import list_response, success_response
from app.scenes import service as scene_service
from app.scenes.schemas import SceneLinkOut, SceneCreate, SceneOut, SceneUpdate

router = APIRouter(tags=["Scenes"])


def _build_scene_out(scene: Scene) -> dict:
    """
    Convert an ORM Scene to a response dict.

    Bridges the name mismatch:
      ORM  → scene.outgoing_links  (list[SceneLink], each with .to_scene loaded)
      JSON → links                 (list[SceneLinkOut] with to_scene_title)

    SceneOut.model_validate uses from_attributes=True so it reads the ORM attrs
    directly, but 'links' field maps to 'outgoing_links' only if we name them the
    same — they're not, so we build the links list manually and inject it.
    """
    base = SceneOut.model_validate(scene).model_dump(by_alias=True)
    # Override with fully-resolved links (to_scene eagerly loaded by service)
    base["links"] = [
        SceneLinkOut.from_orm_with_title(lnk).model_dump()
        for lnk in (scene.outgoing_links or [])
    ]
    return base


@router.get("/tours/{tour_id}/scenes", response_model=dict)
async def list_scenes(
    tour_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    viewer: User | None = Depends(get_current_user_optional),
) -> dict:
    scenes, total = await scene_service.list_scenes(tour_id, db, viewer, page, per_page)
    return list_response(
        [_build_scene_out(s) for s in scenes],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/tours/{tour_id}/scenes", response_model=dict, status_code=201)
async def create_scene(
    tour_id: str,
    body: SceneCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    data = body.model_dump(by_alias=False, exclude_none=True)
    scene = await scene_service.create_scene(tour_id, data, db, cache)
    # Freshly created scene has no links
    scene.outgoing_links = []
    return success_response(_build_scene_out(scene))


@router.get("/scenes/{scene_id}", response_model=dict)
async def get_scene(
    scene_id: str,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache),
) -> dict:
    scene = await scene_service.get_scene(scene_id, db, cache)
    return success_response(scene)


@router.patch("/scenes/{scene_id}", response_model=dict)
async def update_scene(
    scene_id: str,
    body: SceneUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    data = body.model_dump(by_alias=False, exclude_none=True)
    scene = await scene_service.update_scene(scene_id, data, db, cache)
    return success_response(scene)


@router.delete("/scenes/{scene_id}", response_model=dict)
async def delete_scene(
    scene_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    await scene_service.delete_scene(scene_id, db, cache)
    return success_response({"message": "Scene deleted"})


@router.patch("/scenes/{scene_id}/entry-point", response_model=dict)
async def set_entry_point(
    scene_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    scene = await scene_service.set_entry_point(scene_id, db, cache)
    return success_response(scene)
