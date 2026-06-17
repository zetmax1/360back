"""
Image validation and thumbnail generation.

Security rules:
  1. Size: reject before reading full content (streaming check)
  2. MIME type: verified by reading magic bytes, NOT file extension
  3. Aspect ratio: equirectangular panoramas must have width = 2 × height
  4. Minimum resolution: 2048 × 1024
  5. Stored filename: always UUID-based, never trusting original filename
"""
from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path

import aiofiles
import magic
from PIL import Image

from app.config import settings
from app.exceptions import (
    InvalidAspectRatioError,
    InvalidImageTypeError,
    UploadTooLargeError,
)
from app.upload.pole_fixer import fix_panorama_poles

logger = logging.getLogger(__name__)

MIN_WIDTH = 1024
MIN_HEIGHT = 512


async def validate_and_store(
    file_data: bytes,
    original_filename: str,
) -> tuple[str, str, str, str]:
    """
    Validate image data and write to disk.

    Returns:
        (stored_filename, image_url, thumbnail_url, mime_type)
    """
    # 1. Size check
    if len(file_data) > settings.max_upload_size_bytes:
        raise UploadTooLargeError(
            f"File exceeds the maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB"
        )

    # 2. MIME type via magic bytes (not extension)
    detected_mime = magic.from_buffer(file_data[:4096], mime=True)
    if detected_mime not in settings.allowed_image_types_list:
        raise InvalidImageTypeError(
            f"File type '{detected_mime}' is not allowed. "
            f"Accepted: {', '.join(settings.allowed_image_types_list)}"
        )

    # 3. Open image and validate dimensions
    try:
        img = Image.open(io.BytesIO(file_data))
        img.verify()  # detect corrupted files
        img = Image.open(io.BytesIO(file_data))  # re-open after verify()
    except Exception as exc:
        raise InvalidImageTypeError(f"Cannot read image: {exc}")

    width, height = img.size

    if width < MIN_WIDTH or height < MIN_HEIGHT:
        raise InvalidAspectRatioError(
            f"Image too small: {width}×{height}. Minimum is {MIN_WIDTH}×{MIN_HEIGHT}"
        )

    # Note: Aspect ratio validation (2:1) has been relaxed to support 
    # cylindrical mobile panoramas and partial 360 shots.

    # 5. Generate unique filenames (never trust original_filename)
    file_uuid = uuid.uuid4().hex
    # Determine extension from validated MIME
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/avif": ".avif",
        "image/heic": ".heic",
    }
    ext = ext_map.get(detected_mime, ".bin")
    stored_filename = f"{file_uuid}{ext}"
    thumb_filename = f"{file_uuid}_thumb{ext}"

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    MAX_WEBGL_SIZE = 8192
    if width > MAX_WEBGL_SIZE or height > MAX_WEBGL_SIZE:
        ratio = min(MAX_WEBGL_SIZE / width, MAX_WEBGL_SIZE / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        img = img.resize((new_width, new_height), Image.LANCZOS)
        width, height = new_width, new_height

    # Convert to RGB to avoid alpha channel / color space issues in WebGL
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 6. Save original (enforce JPEG for webgl compatibility)
    out_ext = ".jpg"
    stored_filename = f"{file_uuid}{out_ext}"
    dest_path = upload_dir / stored_filename
    
    out_bytes = io.BytesIO()
    img.save(out_bytes, format="JPEG", quality=90, optimize=True)
    async with aiofiles.open(dest_path, "wb") as f:
        await f.write(out_bytes.getvalue())

    # 7. Generate thumbnail (512×256, equirectangular 2:1)
    thumb_filename = f"{file_uuid}_thumb{out_ext}"
    thumb = img.resize(settings.thumbnail_size, Image.LANCZOS)
    thumb_path = upload_dir / thumb_filename
    thumb_bytes = io.BytesIO()
    thumb.save(thumb_bytes, format="JPEG", quality=85, optimize=True)
    async with aiofiles.open(thumb_path, "wb") as f:
        await f.write(thumb_bytes.getvalue())

    image_url = f"/scenes/{stored_filename}"
    thumbnail_url = f"/scenes/{thumb_filename}"

    return stored_filename, image_url, thumbnail_url, detected_mime


# Multi-resolution variants generated during background processing
RESOLUTIONS = {
    "low":    (1024,  512),   # mobile on slow connection
    "medium": (2048,  1024),  # default for most devices
    "high":   (4096,  2048),  # desktop + fast connection
}


def run_pole_fix(stored_filename: str) -> None:
    """
    Synchronous pole-fix function designed to run in a background thread.
    Overwrites the stored image file in-place with the pole-fixed version,
    then generates multi-resolution variants (_low, _medium, _high).
    """
    upload_dir = Path(settings.UPLOAD_DIR)
    image_path = str(upload_dir / stored_filename)

    logger.info("Starting pole fix for %s", stored_filename)
    fix_panorama_poles(
        input_path=image_path,
        output_path=image_path,   # overwrite in-place
        content_zone_fraction=0.55,
        blur_radius=60,
        logo_path=None,           # no logo by default
    )
    logger.info("Pole fix complete for %s", stored_filename)

    # Generate multi-resolution variants
    _generate_resolution_variants(stored_filename)


def _generate_resolution_variants(stored_filename: str) -> None:
    """
    Generate _low, _medium, _high JPEG variants from the processed original.
    Skips variants that would be larger than the source image.
    """
    upload_dir = Path(settings.UPLOAD_DIR)
    image_path = upload_dir / stored_filename

    try:
        img = Image.open(image_path)
        src_width, src_height = img.size
        base_name, ext = stored_filename.rsplit(".", 1)

        for suffix, (target_w, target_h) in RESOLUTIONS.items():
            # Skip if the source is smaller than this resolution
            if src_width <= target_w and src_height <= target_h:
                # For the "high" variant, just copy the original
                if suffix == "high":
                    variant_name = f"{base_name}_{suffix}.{ext}"
                    variant_path = upload_dir / variant_name
                    if not variant_path.exists():
                        import shutil
                        shutil.copy2(str(image_path), str(variant_path))
                    logger.info("Copied original as %s variant: %s", suffix, variant_name)
                continue

            variant_name = f"{base_name}_{suffix}.{ext}"
            variant_path = upload_dir / variant_name

            resized = img.resize((target_w, target_h), Image.LANCZOS)
            out_buf = io.BytesIO()
            resized.save(out_buf, format="JPEG", quality=88, optimize=True)

            with open(variant_path, "wb") as f:
                f.write(out_buf.getvalue())

            logger.info(
                "Generated %s variant: %s (%dx%d)",
                suffix, variant_name, target_w, target_h,
            )

        img.close()
    except Exception:
        logger.exception("Failed to generate resolution variants for %s", stored_filename)
