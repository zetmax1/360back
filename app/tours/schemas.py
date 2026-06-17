"""Tour Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TourCreate(BaseModel):
    slug: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=255)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_default: Optional[bool] = False

    @field_validator("slug", mode="before")
    @classmethod
    def sanitize_slug(cls, v: str) -> str:
        if isinstance(v, str):
            import re
            v = v.strip().lower()
            v = re.sub(r'[\s_]+', '-', v)
            v = re.sub(r'[^a-z0-9\-]', '', v)
        return v


class TourUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_default: Optional[bool] = None


class TourOut(BaseModel):
    id: str
    slug: str
    title: str
    description: Optional[str]
    cover_image_url: Optional[str]
    is_published: bool
    is_default: bool
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TourPublishToggle(BaseModel):
    is_published: bool


class TourDefaultToggle(BaseModel):
    is_default: bool

from app.scenes.schemas import SceneDetailResponse

class TourDetailResponse(TourOut):
    scenes: list[SceneDetailResponse] = []
    scenes_count: int = 0

class TourListItem(TourOut):
    scenes_count: int = 0
    entry_scene_image_url: Optional[str] = None
    entry_scene_thumbnail_url: Optional[str] = None
