from __future__ import annotations

import io
import logging
from pathlib import Path

import requests
from PIL import Image

from app.config import FigureReconstructionConfig, figure_reconstruction_config
from components.scraping.figure_reconstruction import PageImage, reconstruct_page_figures
from domain.image import ArxivFigure

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "linkedin-ml-pipeline/1.0 (educational project)"}

# Minimum image dimensions to consider (filters out icons, thumbnails)
MIN_FIGURE_WIDTH = 200
MIN_FIGURE_HEIGHT = 200


def extract_figures_with_captions(
    arxiv_id: str,
    config: FigureReconstructionConfig | None = None,
) -> list[ArxivFigure]:
    """
    Downloads an arXiv PDF and extracts all figures with their captions.

    Runs the layout-aware figure reconstruction pipeline on each page to
    merge fragmented image XObjects into coherent figure candidates before
    returning them for ranking.

    Args:
        arxiv_id: arXiv paper identifier (e.g. "2310.01234").
        config:   Reconstruction config; uses the global singleton if None.

    Returns:
        List of ArxivFigure ordered by page then figure position. Empty on failure.
    """
    if config is None:
        config = figure_reconstruction_config

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF not installed — skipping figure extraction.")
        return []

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    try:
        response = requests.get(pdf_url, headers=HEADERS, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to download arXiv PDF %s: %s", arxiv_id, exc)
        return []

    try:
        doc = fitz.open(stream=response.content, filetype="pdf")
        figures: list[ArxivFigure] = []
        figure_index = 0

        for page_num, page in enumerate(doc, start=1):
            page_figures = _extract_page_figures(doc, page, page_num, figure_index, config)
            figures.extend(page_figures)
            figure_index += len(page_figures)

        logger.info(
            "Extracted %d figures from arXiv %s (%d pages)",
            len(figures), arxiv_id, len(doc),
        )
        return figures

    except Exception as exc:
        logger.warning("Error processing arXiv PDF %s: %s", arxiv_id, exc)
        return []


def _extract_page_figures(
    doc: "fitz.Document",
    page: "fitz.Page",
    page_num: int,
    figure_index_start: int,
    config: FigureReconstructionConfig,
) -> list[ArxivFigure]:
    """
    Extracts image XObjects from a single PDF page and reconstructs figures.

    Text blocks and raw images are collected first, then handed to
    reconstruct_page_figures which handles clustering, caption alignment,
    and page cropping for multi-image figures.
    """
    # block_type=0 → text, block_type=1 → image
    text_blocks = [
        (b[0], b[1], b[2], b[3], b[4])
        for b in page.get_text("blocks")
        if b[6] == 0
    ]

    page_images: list[PageImage] = []
    for img_ref in page.get_images(full=True):
        xref = img_ref[0]
        base_image = doc.extract_image(xref)
        width = base_image.get("width", 0)
        height = base_image.get("height", 0)

        if width < MIN_FIGURE_WIDTH or height < MIN_FIGURE_HEIGHT:
            continue

        img_rects = page.get_image_rects(xref)
        if not img_rects:
            continue

        rect = img_rects[0]
        page_images.append(PageImage(
            idx=len(page_images),
            rect=(rect.x0, rect.y0, rect.x1, rect.y1),
            image_data=base_image["image"],
            width=width,
            height=height,
        ))

    if not page_images:
        return []

    page_rect = (page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1)
    return reconstruct_page_figures(
        page_images, text_blocks, page_rect, page, page_num, figure_index_start, config
    )


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
