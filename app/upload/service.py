"""Upload business logic."""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import _get_session_factory
from app.exceptions import NotFoundError
from app.models.image_upload import ImageUpload, UploadStatus
from app.upload.image_processor import run_pole_fix, validate_and_store

logger = logging.getLogger(__name__)

# A small thread pool for CPU-bound image processing so we don't block the
# async event loop.
_pole_fix_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pole_fix")


async def upload_scene_image(
    file_data: bytes,
    original_filename: str,
    uploader_id: str,
    db: AsyncSession,
) -> ImageUpload:
    """
    Validate, store, and thumbnail the uploaded panorama.
    Creates an ImageUpload tracking record.

    The image is saved immediately and the response is returned.
    Pole-fix processing runs in the background — the record starts in
    ``processing`` state and transitions to ``ready`` when done.
    """
    # Create a 'pending' record first so we can return an id immediately
    upload_record = ImageUpload(
        original_filename=original_filename,
        stored_filename="",  # filled in after processing
        file_size_bytes=len(file_data),
        mime_type="",
        upload_status=UploadStatus.processing,
        created_by=uploader_id,
    )
    db.add(upload_record)
    await db.flush()  # get the ID

    try:
        stored_filename, image_url, thumbnail_url, detected_mime = (
            await validate_and_store(file_data, original_filename)
        )
        upload_record.stored_filename = stored_filename
        upload_record.mime_type = detected_mime
        # Keep status as 'processing' — the background pole fix will set it to 'ready'
        upload_record.error_message = None
        # Store URLs in the record for easy retrieval
        upload_record.__dict__["_image_url"] = image_url
        upload_record.__dict__["_thumbnail_url"] = thumbnail_url
    except Exception as exc:
        upload_record.upload_status = UploadStatus.failed
        upload_record.error_message = str(exc)
        await db.flush()
        raise

    await db.flush()
    # Attach for response building
    upload_record.__dict__["image_url"] = image_url  # type: ignore[index]
    upload_record.__dict__["thumbnail_url"] = thumbnail_url  # type: ignore[index]

    # ── Launch background pole-fix processing ────────────────────────────
    # We schedule this as an asyncio task so it survives after the response
    # is sent.  The actual CPU-bound work runs in a thread pool.
    upload_id = upload_record.id
    asyncio.create_task(
        _background_pole_fix(upload_id, stored_filename),
        name=f"pole_fix_{upload_id}",
    )

    return upload_record


async def _background_pole_fix(upload_id: str, stored_filename: str) -> None:
    """
    Run pole-fix in a thread pool, then update the DB record.

    Uses its own DB session (the request session is long gone by the time
    this runs).
    """
    loop = asyncio.get_running_loop()
    factory = _get_session_factory()

    try:
        # Run the CPU-bound pole fix in a thread so we don't block the loop
        await loop.run_in_executor(_pole_fix_pool, run_pole_fix, stored_filename)

        # Update DB status → ready
        async with factory() as session:
            record = await session.get(ImageUpload, upload_id)
            if record:
                record.upload_status = UploadStatus.ready
                await session.commit()
                logger.info("Upload %s pole-fix complete → ready", upload_id)

    except Exception as exc:
        logger.exception("Pole fix failed for upload %s: %s", upload_id, exc)
        try:
            async with factory() as session:
                record = await session.get(ImageUpload, upload_id)
                if record:
                    record.upload_status = UploadStatus.failed
                    record.error_message = f"Pole processing failed: {exc}"
                    await session.commit()
        except Exception:
            logger.exception("Failed to update status for upload %s", upload_id)


async def get_upload_status(upload_id: str, db: AsyncSession) -> ImageUpload:
    record = await db.get(ImageUpload, upload_id)
    if not record:
        raise NotFoundError(f"Upload '{upload_id}' not found")
    return record
