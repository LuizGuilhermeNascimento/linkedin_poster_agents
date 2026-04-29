"""
Layout-aware figure reconstruction for PDF pages.

Groups individual image XObjects into coherent figure candidates using
spatial proximity clustering and caption alignment, then renders the merged
bounding box from the page to produce a single cohesive image per figure.

Pipeline:
    raw page images
        → spatial clustering (union-find)
        → caption alignment
        → bbox merge + page crop
        → list[ArxivFigure]
"""
from __future__ import annotations

import io
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import FigureReconstructionConfig
from domain.image import ArxivFigure

if TYPE_CHECKING:
    import fitz
    from PIL.Image import Image as PILImage

logger = logging.getLogger(__name__)

# Matches "Figure 1:", "Figure 2a.", "Fig. 3)" etc.
_CAPTION_RE = re.compile(r"Fig(?:ure)?\.?\s*\d+[a-z]?[:.)]", re.IGNORECASE)


@dataclass
class PageImage:
    """A single image XObject extracted from a PDF page."""
    idx: int
    rect: tuple[float, float, float, float]  # (x0, y0, x1, y1) in PDF points
    image_data: bytes
    width: int
    height: int


def reconstruct_page_figures(
    page_images: list[PageImage],
    text_blocks: list[tuple[float, float, float, float, str]],
    page_rect: tuple[float, float, float, float],
    page: "fitz.Page",
    page_num: int,
    figure_index_start: int,
    config: FigureReconstructionConfig,
) -> list[ArxivFigure]:
    """
    Reconstructs full figures from individual image fragments on a PDF page.

    Single-image clusters pass through unchanged using their raw bytes.
    Multi-image clusters are merged: the union bbox is cropped from a
    rendered page image, preserving vector elements and text labels.

    Args:
        page_images:         Image XObjects with bboxes extracted from the page.
        text_blocks:         Text blocks as (x0, y0, x1, y1, text) tuples.
        page_rect:           Page bounding box (x0, y0, x1, y1) in PDF points.
        page:                PyMuPDF page object (used for rendering).
        page_num:            1-indexed page number.
        figure_index_start:  Starting figure_index for this page.
        config:              Reconstruction configuration.

    Returns:
        List of ArxivFigure, one per reconstructed figure cluster.
    """
    if not page_images:
        return []

    page_x0, page_y0, page_x1, page_y1 = page_rect
    page_w = page_x1 - page_x0
    page_h = page_y1 - page_y0

    captions = _extract_captions(text_blocks) if config.caption_enabled else []

    # Skip clustering when disabled or too few images to form a multi-element figure
    if not config.enabled or len(page_images) < config.min_elements_per_figure:
        return _passthrough_figures(
            page_images, captions, page_h, page_num, figure_index_start, config
        )

    clusters = _cluster_images(page_images, page_w, page_h, config)

    # Render page lazily — only when a multi-image cluster is present
    rendered_page: PILImage | None = None
    figures: list[ArxivFigure] = []

    for cluster_idx, cluster in enumerate(clusters):
        merged_bbox = _merge_bboxes([img.rect for img in cluster])
        caption = _assign_caption(merged_bbox, captions, page_h, config)
        element_count = len(cluster)

        if element_count == 1:
            img = cluster[0]
            confidence = _compute_confidence(1, bool(caption), merged_bbox, page_w, page_h)
            figures.append(ArxivFigure(
                image_data=img.image_data,
                width=img.width,
                height=img.height,
                page_number=page_num,
                figure_index=figure_index_start + cluster_idx,
                caption=caption,
                confidence=confidence,
                element_count=1,
            ))
        else:
            if rendered_page is None:
                rendered_page = _render_page(page, config)

            image_data, width, height = _crop_from_page(
                rendered_page, merged_bbox, page_rect, config
            )

            if image_data is None:
                # Fallback: use the largest raw image in the cluster
                largest = max(cluster, key=lambda x: x.width * x.height)
                image_data = largest.image_data
                width, height = largest.width, largest.height

            confidence = _compute_confidence(element_count, bool(caption), merged_bbox, page_w, page_h)
            figures.append(ArxivFigure(
                image_data=image_data,
                width=width,
                height=height,
                page_number=page_num,
                figure_index=figure_index_start + cluster_idx,
                caption=caption,
                confidence=confidence,
                element_count=element_count,
            ))

    logger.debug(
        "Reconstruction page=%d: %d raw images → %d figures",
        page_num, len(page_images), len(figures),
    )
    return figures


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _passthrough_figures(
    page_images: list[PageImage],
    captions: list[tuple[float, float, float, float, str]],
    page_h: float,
    page_num: int,
    figure_index_start: int,
    config: FigureReconstructionConfig,
) -> list[ArxivFigure]:
    """Converts raw PageImages to ArxivFigure without any clustering."""
    return [
        ArxivFigure(
            image_data=img.image_data,
            width=img.width,
            height=img.height,
            page_number=page_num,
            figure_index=figure_index_start + idx,
            caption=_assign_caption(img.rect, captions, page_h, config),
        )
        for idx, img in enumerate(page_images)
    ]


def _extract_captions(
    text_blocks: list[tuple[float, float, float, float, str]],
) -> list[tuple[float, float, float, float, str]]:
    """Returns text blocks whose content matches a figure caption pattern."""
    return [
        (x0, y0, x1, y1, text.strip())
        for x0, y0, x1, y1, text in text_blocks
        if _CAPTION_RE.search(text.strip())
    ]


def _assign_caption(
    bbox: tuple[float, float, float, float],
    captions: list[tuple[float, float, float, float, str]],
    page_h: float,
    config: FigureReconstructionConfig,
) -> str:
    """Returns the nearest caption below bbox within the max_distance threshold."""
    _, _, _, fig_bottom = bbox
    max_dist = config.caption_max_distance * page_h

    candidates: list[tuple[float, str]] = []
    for _, cy0, _, _, text in captions:
        if cy0 < fig_bottom - 10:  # must start at or below image bottom
            continue
        dist = cy0 - fig_bottom
        if dist <= max_dist:
            candidates.append((dist, text))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0])
    return " ".join(candidates[0][1].split())


def _cluster_images(
    images: list[PageImage],
    page_w: float,
    page_h: float,
    config: FigureReconstructionConfig,
) -> list[list[PageImage]]:
    """
    Groups images into spatial clusters via union-find.

    Two images are connected when both their horizontal and vertical gaps
    are within the configured distance thresholds (relative to page size).
    """
    n = len(images)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    h_threshold = config.distance_threshold * page_w
    v_threshold = config.distance_threshold * page_h

    for i in range(n):
        for j in range(i + 1, n):
            if _are_neighbors(images[i].rect, images[j].rect, h_threshold, v_threshold):
                union(i, j)

    groups: dict[int, list[PageImage]] = defaultdict(list)
    for i, img in enumerate(images):
        groups[find(i)].append(img)

    return list(groups.values())


def _are_neighbors(
    rect_a: tuple[float, float, float, float],
    rect_b: tuple[float, float, float, float],
    h_threshold: float,
    v_threshold: float,
) -> bool:
    """Returns True when two rects are within the proximity thresholds."""
    ax0, ay0, ax1, ay1 = rect_a
    bx0, by0, bx1, by1 = rect_b

    h_gap = max(0.0, max(ax0, bx0) - min(ax1, bx1))
    v_gap = max(0.0, max(ay0, by0) - min(ay1, by1))

    return h_gap <= h_threshold and v_gap <= v_threshold


def _merge_bboxes(
    rects: list[tuple[float, float, float, float]],
) -> tuple[float, float, float, float]:
    """Returns the union bounding box of a list of rects."""
    return (
        min(r[0] for r in rects),
        min(r[1] for r in rects),
        max(r[2] for r in rects),
        max(r[3] for r in rects),
    )


def _render_page(page: "fitz.Page", config: FigureReconstructionConfig) -> "PILImage | None":
    """Renders the PDF page to a PIL Image at the configured DPI."""
    try:
        import fitz
        from PIL import Image

        zoom = config.rendering_dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix)
        return Image.open(io.BytesIO(pix.tobytes("png")))
    except Exception as exc:
        logger.warning("Failed to render page for reconstruction: %s", exc)
        return None


def _crop_from_page(
    page_image: "PILImage | None",
    bbox: tuple[float, float, float, float],
    page_rect: tuple[float, float, float, float],
    config: FigureReconstructionConfig,
) -> tuple[bytes | None, int, int]:
    """
    Crops the figure region from a rendered page image.

    Maps PDF coordinates to pixel coordinates, adds a 1% margin, then
    saves the crop as PNG bytes.

    Returns:
        (png_bytes, width, height) or (None, 0, 0) on failure.
    """
    if page_image is None:
        return None, 0, 0

    try:
        page_x0, page_y0, page_x1, page_y1 = page_rect
        page_w = page_x1 - page_x0
        page_h = page_y1 - page_y0
        img_w, img_h = page_image.size

        scale_x = img_w / page_w
        scale_y = img_h / page_h

        bx0, by0, bx1, by1 = bbox
        margin_x = 0.01 * page_w * scale_x
        margin_y = 0.01 * page_h * scale_y

        px0 = max(0, int((bx0 - page_x0) * scale_x - margin_x))
        py0 = max(0, int((by0 - page_y0) * scale_y - margin_y))
        px1 = min(img_w, int((bx1 - page_x0) * scale_x + margin_x))
        py1 = min(img_h, int((by1 - page_y0) * scale_y + margin_y))

        cropped = page_image.crop((px0, py0, px1, py1)).convert("RGB")
        buf = io.BytesIO()
        cropped.save(buf, "PNG")
        return buf.getvalue(), cropped.width, cropped.height

    except Exception as exc:
        logger.warning("Failed to crop figure from rendered page: %s", exc)
        return None, 0, 0


def _compute_confidence(
    element_count: int,
    has_caption: bool,
    bbox: tuple[float, float, float, float],
    page_w: float,
    page_h: float,
) -> float:
    """
    Scores reconstruction confidence in [0, 1].

    Weighted combination of:
    - Element count (40%): more fragments merged → higher confidence, capped
    - Caption presence (40%): known figure label is a strong signal
    - Area coverage (20%): ideal range 5%–40% of page area
    """
    element_score = min(1.0, 0.5 + 0.25 * (element_count - 1))
    caption_score = 1.0 if has_caption else 0.6

    bw = bbox[2] - bbox[0]
    bh = bbox[3] - bbox[1]
    area_ratio = (bw * bh) / max(1.0, page_w * page_h)

    if area_ratio < 0.05:
        area_score = area_ratio / 0.05
    elif area_ratio > 0.40:
        area_score = max(0.3, 1.0 - (area_ratio - 0.40) / 0.60)
    else:
        area_score = 1.0

    return round(element_score * 0.4 + caption_score * 0.4 + area_score * 0.2, 3)
