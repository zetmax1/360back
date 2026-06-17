"""SceneLink Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class LinkCreate(BaseModel):
    to_scene_id: str
    degree: float = Field(..., ge=0.0, lt=360.0)
    label: Optional[str] = Field(None, max_length=255)

    @field_validator("degree")
    @classmethod
    def validate_degree(cls, v: float) -> float:
        if not (0.0 <= v < 360.0):
            raise ValueError("degree must be in range [0, 360)")
        return v


class LinkUpdate(BaseModel):
    degree: Optional[float] = Field(None, ge=0.0, lt=360.0)
    label: Optional[str] = Field(None, max_length=255)

    @field_validator("degree")
    @classmethod
    def validate_degree(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v < 360.0):
            raise ValueError("degree must be in range [0, 360)")
        return v


class LinkOut(BaseModel):
    id: str
    from_scene_id: str
    to_scene_id: str
    to_scene_title: str  # resolved from to_scene relationship
    degree: float
    label: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_title(cls, link: Any) -> "LinkOut":
        return cls(
            id=link.id,
            from_scene_id=link.from_scene_id,
            to_scene_id=link.to_scene_id,
            to_scene_title=link.to_scene.title if link.to_scene else "",
            degree=link.degree,
            label=link.label,
            created_at=link.created_at,
        )
