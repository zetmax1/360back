"""
Panorama Pole Fixer — replaces distorted top/bottom bands of an
equirectangular panorama with a softly blurred fill derived from the
edge of the real content zone.

Pillow-only (no OpenCV).  Can be imported or run from the command line:

    python -m app.upload.pole_fixer input.jpg output.jpg --content-zone 0.55 --blur 60 --logo logo.png

How it works:
    1. The "content zone" is the vertical band in the middle that has real
       photo data (e.g. the middle 55 % of height for phone-stitched panos).
    2. A thin strip at the top/bottom edge of the content zone is sampled,
       heavily blurred, and stretched to fill the empty band above/below.
    3. A vertical gradient alpha mask smoothly blends the blurred fill into
       the real content so there is no visible seam.
    4. Optionally, a circular logo/watermark is composited at the exact
       zenith and nadir points (the worst-looking pixels).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from PIL import Image, ImageFilter, ImageDraw

logger = logging.getLogger(__name__)


def fix_panorama_poles(
    input_path: str,
    output_path: str,
    content_zone_fraction: float = 0.55,
    blur_radius: int = 60,
    logo_path: str | None = None,
    logo_size_fraction: float = 0.08,
) -> None:
    """
    Replace the distorted top and bottom poles of an equirectangular panorama
    with a softly blurred fill derived from the edge of the real content zone.
    Optionally adds a logo patch at the exact zenith and nadir points.

    Args:
        input_path: Path to the source equirectangular JPEG/PNG.
        output_path: Where to write the processed JPEG.
        content_zone_fraction: What fraction of the image height has real
            photo content (0.0–1.0).  0.55 means the middle 55 % is real.
        blur_radius: Gaussian blur radius for the fill patches.
        logo_path: Optional path to a circular logo PNG with alpha channel.
        logo_size_fraction: Logo diameter as a fraction of image width.
    """
    img = Image.open(input_path).convert("RGB")
    width, height = img.size

    # ── Compute content zone boundaries ──────────────────────────────────
    empty_fraction = 1.0 - content_zone_fraction
    top_band_height = int(height * empty_fraction / 2)      # pixels above content
    bottom_band_start = height - top_band_height             # pixel row where bottom band begins

    # Nothing to fix if the content zone covers the whole image
    if top_band_height < 4:
        logger.info("Content zone covers the entire image — nothing to fix.")
        img.save(output_path, format="JPEG", quality=92, optimize=True)
        return

    # ── How many rows to sample from the edge of the real content ────────
    sample_rows = max(8, top_band_height // 4)

    # ── Fix the TOP band ─────────────────────────────────────────────────
    _fill_band(
        img,
        band_top=0,
        band_bottom=top_band_height,
        sample_y_start=top_band_height,
        sample_y_end=top_band_height + sample_rows,
        blur_radius=blur_radius,
        flip_gradient=True,   # gradient goes from opaque (near content) → transparent (pole)
    )

    # ── Fix the BOTTOM band ──────────────────────────────────────────────
    _fill_band(
        img,
        band_top=bottom_band_start,
        band_bottom=height,
        sample_y_start=bottom_band_start - sample_rows,
        sample_y_end=bottom_band_start,
        blur_radius=blur_radius,
        flip_gradient=False,
    )

    # ── Optional logo at zenith and nadir ────────────────────────────────
    if logo_path and Path(logo_path).exists():
        _stamp_logo(img, logo_path, logo_size_fraction, top_band_height, bottom_band_start)

    # ── Save ─────────────────────────────────────────────────────────────
    img.save(output_path, format="JPEG", quality=92, optimize=True)
    logger.info("Pole-fixed panorama saved to %s", output_path)


# ── Internal helpers ─────────────────────────────────────────────────────────


def _fill_band(
    img: Image.Image,
    band_top: int,
    band_bottom: int,
    sample_y_start: int,
    sample_y_end: int,
    blur_radius: int,
    flip_gradient: bool,
) -> None:
    """
    Fill a horizontal band of *img* (in-place) with a blurred, gradient-
    blended version of a sample strip taken from the edge of the real content.
    """
    width, height = img.size
    band_height = band_bottom - band_top
    if band_height <= 0:
        return

    # 1. Crop the thin sample strip from the real content edge
    strip = img.crop((0, sample_y_start, width, sample_y_end))

    # 2. Stretch it to fill the entire band height.
    #    Using Image.BOX instead of Image.BILINEAR is much faster and the difference
    #    is imperceptible since we're going to heavily blur it anyway.
    stretched = strip.resize((width, band_height), Image.BOX)

    # 3. Apply heavy blur. 
    #    Since we just stretched a thin strip vertically, we only really need to blur
    #    horizontally to smear the colors across the pole. We can significantly reduce 
    #    the blur radius (e.g., from 60 to 30) since the stretch already blurred it vertically.
    #    Using BoxBlur instead of GaussianBlur is much faster and looks the same here.
    fast_blur_radius = max(5, blur_radius // 2)
    blurred = stretched.filter(ImageFilter.BoxBlur(radius=fast_blur_radius))

    # 4. Create a gradient alpha mask for smooth blending.
    #    Instead of looping per pixel in Python, we use Pillow's Image.linear_gradient
    gradient_img = Image.linear_gradient("L")  # 256x256 linear gradient 0 to 255
    if flip_gradient:
        # Top band: black at bottom (content edge, alpha=0), white at top (pole, alpha=255)
        # We can just rotate 180 instead of flip which is slightly faster
        gradient = gradient_img.rotate(180).resize((width, band_height), Image.BILINEAR)
    else:
        # Bottom band: black at top (content edge, alpha=0), white at bottom (pole, alpha=255)
        gradient = gradient_img.resize((width, band_height), Image.BILINEAR)

    # 5. Composite: paste blurred fill over the existing content using the gradient mask
    band_region = img.crop((0, band_top, width, band_bottom))
    composited = Image.composite(blurred, band_region, gradient)
    img.paste(composited, (0, band_top))


def _stamp_logo(
    img: Image.Image,
    logo_path: str,
    size_fraction: float,
    top_band_height: int,
    bottom_band_start: int,
) -> None:
    """Paste a circular logo at the zenith (top band center) and nadir (bottom band center)."""
    width, height = img.size
    logo_size = max(32, int(width * size_fraction))

    logo = Image.open(logo_path).convert("RGBA")
    logo = logo.resize((logo_size, logo_size), Image.LANCZOS)

    # Create a circular mask if the logo doesn't already have good alpha
    circle_mask = Image.new("L", (logo_size, logo_size), 0)
    draw = ImageDraw.Draw(circle_mask)
    draw.ellipse((0, 0, logo_size - 1, logo_size - 1), fill=255)

    # Use the logo's own alpha intersected with the circle (fast using ImageChops)
    if logo.mode == "RGBA":
        from PIL import ImageChops
        logo_alpha = logo.split()[3]
        mask = ImageChops.multiply(logo_alpha, circle_mask)
    else:
        mask = circle_mask

    logo_rgb = logo.convert("RGB")

    # Zenith (center of top band)
    zenith_x = (width - logo_size) // 2
    zenith_y = (top_band_height - logo_size) // 2
    if zenith_y >= 0:
        img.paste(logo_rgb, (zenith_x, zenith_y), mask)

    # Nadir (center of bottom band)
    nadir_x = (width - logo_size) // 2
    nadir_y = bottom_band_start + (height - bottom_band_start - logo_size) // 2
    if nadir_y >= 0 and nadir_y + logo_size <= height:
        img.paste(logo_rgb, (nadir_x, nadir_y), mask)

    logger.info("Stamped logo at zenith (%d, %d) and nadir (%d, %d)", zenith_x, zenith_y, nadir_x, nadir_y)


# ── CLI ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix polar distortion in equirectangular panoramas.",
    )
    parser.add_argument("input", help="Input equirectangular image path")
    parser.add_argument("output", help="Output image path")
    parser.add_argument(
        "--content-zone", type=float, default=0.55,
        help="Fraction of height that has real content (default: 0.55)",
    )
    parser.add_argument(
        "--blur", type=int, default=60,
        help="Gaussian blur radius for pole fill (default: 60)",
    )
    parser.add_argument(
        "--logo", default=None,
        help="Path to a circular logo PNG (RGBA) to stamp at zenith/nadir",
    )
    parser.add_argument(
        "--logo-size", type=float, default=0.08,
        help="Logo diameter as fraction of image width (default: 0.08)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    fix_panorama_poles(
        input_path=args.input,
        output_path=args.output,
        content_zone_fraction=args.content_zone,
        blur_radius=args.blur,
        logo_path=args.logo,
        logo_size_fraction=args.logo_size,
    )
    logger.info("✓ Pole-fixed panorama saved to %s", args.output)


if __name__ == "__main__":
    main()
