"""Scene Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SceneCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    image_url: str = Field(..., min_length=1, max_length=1024)
    thumbnail_url: Optional[str] = None
    initial_yaw: float = Field(0.0, ge=0.0, lt=360.0)
    order_index: int = Field(0, ge=0)
    is_entry_point: bool = False
    metadata_: Optional[dict[str, Any]] = Field(None, alias="metadata")

    model_config = {"populate_by_name": True}


class SceneUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    image_url: Optional[str] = Field(None, max_length=1024)
    thumbnail_url: Optional[str] = None
    initial_yaw: Optional[float] = Field(None, ge=0.0, lt=360.0)
    order_index: Optional[int] = Field(None, ge=0)
    metadata_: Optional[dict[str, Any]] = Field(None, alias="metadata")

    model_config = {"populate_by_name": True}


class SceneLinkOut(BaseModel):
    """Link schema embedded in SceneOut — includes to_scene fields for the frontend cursor + preloading."""
    id: str
    from_scene_id: str
    to_scene_id: str
    to_scene_title: str  # populated from the to_scene relationship
    to_scene_image_url: str  # for preloading the next scene's panorama
    to_scene_thumbnail_url: Optional[str]  # for blur-up placeholder
    degree: float
    label: Optional[str]

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_title(cls, link: Any) -> "SceneLinkOut":
        """Build the schema and resolve to_scene fields from the ORM relationship."""
        to_scene = link.to_scene
        return cls(
            id=link.id,
            from_scene_id=link.from_scene_id,
            to_scene_id=link.to_scene_id,
            to_scene_title=to_scene.title if to_scene else "",
            to_scene_image_url=to_scene.image_url if to_scene else "",
            to_scene_thumbnail_url=to_scene.thumbnail_url if to_scene else None,
            degree=link.degree,
            label=link.label,
        )


class SceneOut(BaseModel):
    id: str
    tour_id: str
    title: str
    description: Optional[str]
    image_url: str
    thumbnail_url: Optional[str]
    initial_yaw: float
    order_index: int
    is_entry_point: bool
    links: list[SceneLinkOut] = Field(default_factory=list)
    metadata: Optional[dict[str, Any]] = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

class SceneDetailResponse(SceneOut):
    pass
