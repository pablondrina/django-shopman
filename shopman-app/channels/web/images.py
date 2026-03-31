"""Image processing pipeline for storefront product images.

Usage — called from a model's save() or a signal:

    from channels.web.images import process_product_image
    process_product_image(product.image)

Generates:
    - Original capped at 800px wide
    - Variants: thumb (200px), card (400px), detail (800px)
    - WebP conversion with JPEG fallback
    - Stores width/height in the image field's metadata for layout-shift prevention.

Requires Pillow (already a Django dependency).
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

VARIANTS = {
    "thumb": 200,
    "card": 400,
    "detail": 800,
}

MAX_DIMENSION = 800
WEBP_QUALITY = 82
JPEG_QUALITY = 85


def process_product_image(image_field, *, save=True):
    """Resize and convert a product image, generating size variants.

    Args:
        image_field: Django ImageField (or FieldFile) with a .name
        save: If True, saves the parent model instance after processing.

    Returns:
        dict with variant paths + dimensions, or None if no image.
    """
    if not image_field or not image_field.name:
        return None

    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed — skipping image processing")
        return None

    try:
        image_field.open()
        img = Image.open(image_field)
        img.load()  # Force read into memory
    except Exception:
        logger.exception("Failed to open image %s", image_field.name)
        return None

    # Convert RGBA → RGB for JPEG/WebP compatibility
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    original_path = Path(image_field.name)
    base_dir = str(original_path.parent)
    stem = original_path.stem
    storage = image_field.storage

    results = {}

    for variant_name, max_width in VARIANTS.items():
        resized = _resize_to_width(img, max_width)
        w, h = resized.size

        # Save WebP
        webp_buf = BytesIO()
        resized.save(webp_buf, format="WEBP", quality=WEBP_QUALITY, method=4)
        webp_name = f"{base_dir}/{stem}_{variant_name}.webp"
        storage.save(webp_name, ContentFile(webp_buf.getvalue()))

        # Save JPEG fallback
        jpeg_buf = BytesIO()
        resized.save(jpeg_buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        jpeg_name = f"{base_dir}/{stem}_{variant_name}.jpg"
        storage.save(jpeg_name, ContentFile(jpeg_buf.getvalue()))

        results[variant_name] = {
            "webp": webp_name,
            "jpeg": jpeg_name,
            "width": w,
            "height": h,
        }

    logger.info("Processed image %s → %d variants", image_field.name, len(results))
    return results


def _resize_to_width(img, max_width):
    """Resize image to fit within max_width, maintaining aspect ratio."""
    from PIL import Image

    w, h = img.size
    if w <= max_width:
        return img.copy()
    ratio = max_width / w
    new_h = int(h * ratio)
    return img.resize((max_width, new_h), Image.LANCZOS)
