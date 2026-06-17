"""Upload router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import require_admin
from app.exceptions import UploadTooLargeError
from app.models.user import User
from app.responses import success_response
from app.upload import service as upload_service
from app.upload.schemas import UploadOut, UploadStatusOut

router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post("/scene-image", response_model=dict, status_code=201)
async def upload_scene_image(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """
    Upload a panorama image for a scene.

    Validates:
      - File size ≤ MAX_UPLOAD_SIZE_MB
      - MIME type via magic bytes (jpeg, png, or webp)
      - Dimensions: width = 2 × height (equirectangular)
      - Minimum resolution: 2048 × 1024

    Returns upload_id, image_url, thumbnail_url, and status.
    The image undergoes background pole-fix processing — poll
    GET /upload/{upload_id}/status until status is 'ready'.
    Link to a scene later via PATCH /scenes/{id}.
    """
    # Read file into memory (with size guard)
    file_data = await file.read(settings.max_upload_size_bytes + 1)
    if len(file_data) > settings.max_upload_size_bytes:
        raise UploadTooLargeError(
            f"File exceeds the maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB"
        )

    upload = await upload_service.upload_scene_image(
        file_data=file_data,
        original_filename=file.filename or "upload",
        uploader_id=admin.id,
        db=db,
    )

    return success_response(
        {
            "upload_id": upload.id,
            "image_url": upload.__dict__.get("image_url", ""),
            "thumbnail_url": upload.__dict__.get("thumbnail_url", ""),
            "status": upload.upload_status,
        }
    )


@router.get("/{upload_id}/status", response_model=dict)
async def get_upload_status(
    upload_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Poll the processing status of an upload."""
    record = await upload_service.get_upload_status(upload_id, db)

    # Build the image/thumbnail URLs from stored_filename so the frontend
    # can show the preview once processing is complete.
    image_url = f"/scenes/{record.stored_filename}" if record.stored_filename else None
    thumbnail_url = None
    if record.stored_filename:
        # Thumbnail follows the convention: <uuid>_thumb.jpg
        base = record.stored_filename.rsplit(".", 1)
        if len(base) == 2:
            thumbnail_url = f"/scenes/{base[0]}_thumb.{base[1]}"

    data = {
        "upload_id": record.id,
        "status": record.upload_status,
        "original_filename": record.original_filename,
        "file_size_bytes": record.file_size_bytes,
        "mime_type": record.mime_type,
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
        "error_message": record.error_message,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
    return success_response(data)
