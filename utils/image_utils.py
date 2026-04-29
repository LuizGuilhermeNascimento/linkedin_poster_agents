from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

LINKEDIN_TARGET_WIDTH = 1200


def postprocess_image(image_path: Path, target_width: int = LINKEDIN_TARGET_WIDTH) -> None:
    """
    Resizes and optimizes an image for LinkedIn.

    Operations:
    - Resize to target_width while maintaining aspect ratio (only if larger)
    - Convert to RGB (strips alpha channel)
    - Save as PNG

    Modifies the file in-place. Silently skips if the file doesn't exist or
    cannot be opened.
    """
    if not image_path.exists():
        return

    try:
        img = Image.open(image_path).convert("RGB")
        if img.width > target_width:
            ratio = target_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((target_width, new_height), Image.LANCZOS)
            logger.debug("Resized image to %dx%d", target_width, new_height)
        img.save(image_path, "PNG", optimize=True)
    except Exception as exc:
        logger.warning("Failed to postprocess image %s: %s", image_path, exc)


def crop_center(image_path: Path, target_width: int, target_height: int) -> None:
    """
    Center-crops an image to the target dimensions.

    Modifies the file in-place. Silently skips if dimensions are already correct.
    """
    if not image_path.exists():
        return

    try:
        img = Image.open(image_path).convert("RGB")
        src_w, src_h = img.size

        if src_w == target_width and src_h == target_height:
            return

        # Scale to fit the target dimensions while covering both dimensions
        scale = max(target_width / src_w, target_height / src_h)
        scaled_w = int(src_w * scale)
        scaled_h = int(src_h * scale)
        img = img.resize((scaled_w, scaled_h), Image.LANCZOS)

        left = (scaled_w - target_width) // 2
        top = (scaled_h - target_height) // 2
        img = img.crop((left, top, left + target_width, top + target_height))
        img.save(image_path, "PNG", optimize=True)
    except Exception as exc:
        logger.warning("Failed to crop image %s: %s", image_path, exc)
