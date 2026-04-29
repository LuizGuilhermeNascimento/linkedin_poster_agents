"""
Ranks arXiv PDF figures by relevance to the LinkedIn post context.

Score formula:
    score = semantic_weight * semantic
          + keyword_weight  * keyword_boost
          + position_weight * position_heuristic

Visual noise filter rejects figures whose captions mention real-world
scene content (cars, streets, buildings, people) before scoring.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

from domain.image import ArxivFigure

logger = logging.getLogger(__name__)

# Keywords that indicate a relevant ML/architecture figure
_POSITIVE_KW = re.compile(
    r"\b(architecture|framework|method|pipeline|model|memory|attention|"
    r"transformer|encoder|decoder|layer|module|block|mechanism|network|"
    r"overview|system|approach|design|structure|workflow|diagram)\b",
    re.IGNORECASE,
)

# Keywords that indicate a less-relevant figure (results, baselines, real-world)
_NEGATIVE_KW = re.compile(
    r"\b(dataset|scene|results|reconstruction|baseline|comparison|ablation|"
    r"performance|accuracy|metric|evaluation|benchmark|table|plot|curve|"
    r"visualization|qualitative|quantitative)\b",
    re.IGNORECASE,
)

# Visual noise: reject figures whose captions reference real-world scenes
_VISUAL_NOISE_KW = re.compile(
    r"\b(car|cars|street|streets|building|buildings|person|people|human|"
    r"pedestrian|traffic|road|vehicle|face|faces|crowd|outdoor|indoor|"
    r"cityscape|landscape|photograph|photo|real.world|autonomous|driving|"
    r"object detection|segmentation mask)\b",
    re.IGNORECASE,
)

# Score weights (must sum to 1.0)
# reconstruction: confidence from figure_reconstruction (1.0 for non-reconstructed figures)
_WEIGHTS = {
    "semantic": 0.40,
    "keyword": 0.27,
    "position": 0.22,
    "reconstruction": 0.11,
}

# Position boost applies to figures on pages 1-N; decay after
_POSITION_BOOST_PAGES = 3


@dataclass
class FigureScore:
    figure: ArxivFigure
    total: float
    semantic: float
    keyword: float
    position: float
    rejected: bool = False
    rejection_reason: str = ""


def rank_and_select(
    figures: list[ArxivFigure],
    post_summary: str,
    post_angle: str,
    min_score: float = 0.0,
) -> tuple[ArxivFigure | None, list[FigureScore]]:
    """
    Ranks figures by relevance to the post context and selects the best one.

    Args:
        figures: All figures extracted from the arXiv PDF.
        post_summary: Summary of the paper.
        post_angle: Framing/angle of the LinkedIn post.
        min_score: Minimum composite score required to accept a figure.

    Returns:
        (best_figure, all_scored) — best_figure is None if no valid figure
        meets the min_score threshold.
    """
    if not figures:
        logger.info("Figure ranker: no figures provided")
        return None, []

    post_context = f"{post_summary} {post_angle}"
    total_pages = max(f.page_number for f in figures)

    scored: list[FigureScore] = []
    for figure in figures:
        fs = _score_figure(figure, post_context, total_pages)
        scored.append(fs)
        logger.debug(
            "Figure page=%d idx=%d score=%.3f "
            "(sem=%.3f kw=%.3f pos=%.3f) rejected=%s reason=%r caption=%r",
            figure.page_number, figure.figure_index,
            fs.total, fs.semantic, fs.keyword, fs.position,
            fs.rejected, fs.rejection_reason,
            figure.caption[:80],
        )

    valid = [s for s in scored if not s.rejected]
    rejected = [s for s in scored if s.rejected]

    logger.info(
        "Figure ranker: total=%d valid=%d rejected=%d",
        len(scored), len(valid), len(rejected),
    )
    for s in rejected:
        logger.info(
            "  Rejected [page=%d idx=%d]: %s",
            s.figure.page_number, s.figure.figure_index, s.rejection_reason,
        )

    valid.sort(key=lambda s: s.total, reverse=True)

    if valid and valid[0].total >= min_score:
        best = valid[0]
        logger.info(
            "Selected figure: page=%d idx=%d score=%.3f caption=%r",
            best.figure.page_number, best.figure.figure_index,
            best.total, best.figure.caption[:80],
        )
        return best.figure, scored

    logger.info("No valid figure above min_score=%.2f", min_score)
    return None, scored


def _score_figure(figure: ArxivFigure, post_context: str, total_pages: int) -> FigureScore:
    if _is_visual_noise(figure.caption):
        reason = _visual_noise_reason(figure.caption)
        return FigureScore(
            figure=figure, total=0.0,
            semantic=0.0, keyword=0.0, position=0.0,
            rejected=True, rejection_reason=reason,
        )

    semantic = _semantic_score(figure.caption, post_context)
    keyword = _keyword_score(figure.caption)
    position = _position_score(figure.page_number, total_pages)

    total = (
        _WEIGHTS["semantic"] * semantic
        + _WEIGHTS["keyword"] * keyword
        + _WEIGHTS["position"] * position
        + _WEIGHTS["reconstruction"] * figure.confidence
    )

    return FigureScore(
        figure=figure, total=total,
        semantic=semantic, keyword=keyword, position=position,
    )


def _is_visual_noise(caption: str) -> bool:
    return bool(_VISUAL_NOISE_KW.search(caption))


def _visual_noise_reason(caption: str) -> str:
    matches = _VISUAL_NOISE_KW.findall(caption)
    unique = ", ".join(sorted(set(m.lower() for m in matches)))
    return f"visual noise keywords: {unique}"


def _semantic_score(caption: str, post_context: str) -> float:
    """
    Bag-of-words cosine similarity between the figure caption and the post context.

    Returns 0.4 for figures without a caption (slight penalty, not zero).
    """
    if not caption.strip():
        return 0.4
    return _bow_cosine(caption, post_context)


def _keyword_score(caption: str) -> float:
    """
    Positive keywords boost the score; negative keywords penalize it.

    Returns a value in [0, 1].
    """
    positive = len(_POSITIVE_KW.findall(caption))
    negative = len(_NEGATIVE_KW.findall(caption))
    # Raw score: 3+ positives saturates to 1.0; each negative costs 0.5
    raw = positive - 0.5 * negative
    return max(0.0, min(1.0, (raw + 1.0) / 4.0))


def _position_score(page_number: int, total_pages: int) -> float:
    """
    Earlier figures score higher. Pages 1–3 get the maximum boost.
    Score decays linearly from 1.0 (page 1) to 0.3 (last page).
    """
    if total_pages <= 1:
        return 1.0
    normalized = (page_number - 1) / max(1, total_pages - 1)
    return 1.0 - 0.7 * normalized


def _bow_cosine(text_a: str, text_b: str) -> float:
    """
    Cosine similarity using bag-of-words (words ≥ 4 characters, lowercased).

    Short words (stopwords, articles) are excluded by the length filter.
    """
    def tokenize(text: str) -> Counter:
        return Counter(re.findall(r"\b[a-z]{4,}\b", text.lower()))

    vec_a = tokenize(text_a)
    vec_b = tokenize(text_b)

    if not vec_a or not vec_b:
        return 0.0

    common = set(vec_a) & set(vec_b)
    dot = sum(vec_a[k] * vec_b[k] for k in common)
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)
