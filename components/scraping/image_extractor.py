from __future__ import annotations

import io
import logging
from pathlib import Path

import requests
from PIL import Image

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "linkedin-ml-pipeline/1.0 (educational project)"}


def extract_first_figure_from_arxiv(arxiv_id: str, output_path: Path) -> bool:
    """
    Downloads the arXiv PDF and extracts the first relevant figure.

    Returns:
        True if an image was saved, False otherwise.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not installed — skipping figure extraction.")
        return False

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    try:
        response = requests.get(pdf_url, headers=HEADERS, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to download arXiv PDF %s: %s", arxiv_id, exc)
        return False

    try:
        doc = fitz.open(stream=response.content, filetype="pdf")
        for page in doc:
            for img_ref in page.get_images(full=True):
                xref = img_ref[0]
                base_image = doc.extract_image(xref)
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)
                if width < 200 or height < 200:
                    continue
                img = Image.open(io.BytesIO(base_image["image"])).convert("RGB")
                img.save(output_path, "PNG")
                logger.info("Figure extracted from arXiv %s → %s", arxiv_id, output_path)
                return True
    except Exception as exc:
        logger.warning("Error processing arXiv PDF %s: %s", arxiv_id, exc)

    return False


def download_image(image_url: str, output_path: Path, max_retries: int = 3) -> bool:
    """
    Downloads an image from a URL and saves it as PNG.

    Handles 429 rate-limiting with retry logic.

    Returns:
        True if saved successfully, False otherwise.
    """
    import time

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(image_url, headers=HEADERS, timeout=30)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                logger.warning(
                    "429 Too Many Requests for %s — waiting %ds (attempt %d/%d)",
                    image_url, retry_after, attempt, max_retries,
                )
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content)).convert("RGB")
            img.save(output_path, "PNG")
            return True
        except requests.HTTPError:
            raise
        except Exception as exc:
            logger.warning("Failed to download image %s: %s", image_url, exc)
            return False

    logger.warning("Failed to download %s after %d attempts (429)", image_url, max_retries)
    return False


def get_image_dimensions(image_url: str, timeout: int = 15) -> tuple[int, int]:
    """
    Downloads an image and returns (width, height). Returns (0, 0) on failure.
    """
    try:
        response = requests.get(image_url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        img = Image.open(io.BytesIO(response.content))
        return img.size  # (width, height)
    except Exception as exc:
        logger.debug("Could not get dimensions for %s: %s", image_url, exc)
        return 0, 0
