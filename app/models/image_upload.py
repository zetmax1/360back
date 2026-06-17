"""ImageUpload tracking model — records every upload attempt."""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class UploadStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class ImageUpload(Base, TimestampMixin):
    __tablename__ = "image_uploads"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    # Nullable while upload is still in progress / not yet linked to a scene
    scene_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("scenes.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    upload_status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status"),
        nullable=False,
        default=UploadStatus.pending,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    uploader: Mapped["User"] = relationship(  # noqa: F821
        "User", back_populates="uploads", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<ImageUpload id={self.id} status={self.upload_status}>"
