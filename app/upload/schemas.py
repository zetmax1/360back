"""Upload Pydantic schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.image_upload import UploadStatus


class UploadOut(BaseModel):
    upload_id: str
    image_url: str
    thumbnail_url: str
    status: UploadStatus

    model_config = {"from_attributes": True}


class UploadStatusOut(BaseModel):
    upload_id: str
    status: UploadStatus
    original_filename: str
    file_size_bytes: int
    mime_type: str
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
