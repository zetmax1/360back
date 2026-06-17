"""Links router."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, get_cache
from app.cache.service import CacheService
from app.links import service as link_service
from app.links.schemas import LinkCreate, LinkOut, LinkUpdate
from app.models.user import User
from app.responses import list_response, success_response

router = APIRouter(tags=["Links"])


@router.get("/scenes/{scene_id}/links", response_model=dict)
async def list_links(
    scene_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    links = await link_service.list_links(scene_id, db)
    return list_response(
        [LinkOut.from_orm_with_title(lnk).model_dump() for lnk in links],
        total=len(links),
    )


@router.post("/scenes/{scene_id}/links", response_model=dict, status_code=201)
async def create_link(
    scene_id: str,
    body: LinkCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    link = await link_service.create_link(scene_id, body.model_dump(), db, cache)
    return success_response(LinkOut.from_orm_with_title(link).model_dump())


@router.patch("/links/{link_id}", response_model=dict)
async def update_link(
    link_id: str,
    body: LinkUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    link = await link_service.update_link(
        link_id, body.model_dump(exclude_none=True), db, cache
    )
    return success_response(LinkOut.from_orm_with_title(link).model_dump())


@router.delete("/links/{link_id}", response_model=dict)
async def delete_link(
    link_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    cache: CacheService = Depends(get_cache),
) -> dict:
    await link_service.delete_link(link_id, db, cache)
    return success_response({"message": "Link deleted"})
