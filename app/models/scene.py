"""Scene model — a single physical location with one equirectangular panorama."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Scene(Base, TimestampMixin):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tour_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tours.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Panorama image (equirectangular, width = 2 × height)
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Viewer defaults
    initial_yaw: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_entry_point: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Arbitrary metadata (GPS coords, floor number, custom tags, …)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True, default=None
    )

    # Relationships
    tour: Mapped["Tour"] = relationship(  # noqa: F821
        "Tour", back_populates="scenes", lazy="noload"
    )
    outgoing_links: Mapped[list["SceneLink"]] = relationship(  # noqa: F821
        "SceneLink",
        foreign_keys="SceneLink.from_scene_id",
        back_populates="from_scene",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    incoming_links: Mapped[list["SceneLink"]] = relationship(  # noqa: F821
        "SceneLink",
        foreign_keys="SceneLink.to_scene_id",
        back_populates="to_scene",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Scene id={self.id} title={self.title}>"
