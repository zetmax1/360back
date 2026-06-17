"""
SceneLink model — directional connection between two scenes.

The `degree` field is the *compass bearing* (0–359.9°) at which the
arrow/cursor is rendered on the panorama of `from_scene`.
  0°   = north / forward
  90°  = right
  180° = south / behind the viewer
  270° = left

This allows the frontend to overlay directional navigation arrows at
the exact compass position, just like Google Street View's blue arrows.
"""
from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class SceneLink(Base, TimestampMixin):
    __tablename__ = "scene_links"

    __table_args__ = (
        # One directed link per scene pair (no duplicate arrows)
        UniqueConstraint("from_scene_id", "to_scene_id", name="uq_scene_link_pair"),
        # Degree must be in [0, 360)
        CheckConstraint("degree >= 0 AND degree < 360", name="ck_scene_link_degree"),
        # A scene cannot link to itself
        CheckConstraint(
            "from_scene_id != to_scene_id", name="ck_scene_link_no_self_ref"
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    from_scene_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("scenes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_scene_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("scenes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Compass bearing for the navigation arrow on the panorama
    degree: Mapped[float] = mapped_column(Float, nullable=False)
    # Optional tooltip shown on the arrow (e.g. "Room 3", "Exit")
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    from_scene: Mapped["Scene"] = relationship(  # noqa: F821
        "Scene",
        foreign_keys=[from_scene_id],
        back_populates="outgoing_links",
        lazy="noload",
    )
    to_scene: Mapped["Scene"] = relationship(  # noqa: F821
        "Scene",
        foreign_keys=[to_scene_id],
        back_populates="incoming_links",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<SceneLink {self.from_scene_id} → {self.to_scene_id} @ {self.degree}°>"
        )
