from __future__ import annotations

from domain.image import ImageCandidate, ScoredCandidate
from .classifier import classify

# LinkedIn ideal aspect ratios
LINKEDIN_IDEAL_RATIOS = [
    (1.91, 1.0),  # horizontal (1200x628)
    (1.0, 1.0),   # square (1080x1080)
]
RATIO_TOLERANCE = 0.3

SOURCE_SCORES: dict[str, float] = {
    "github": 1.0,
    "huggingface": 0.9,
    "web": 0.8,
    "arxiv": 0.85,
    "unsplash": 0.6,
}

VISUAL_TYPE_MATCH: dict[tuple[str, str], float] = {
    ("diagram", "diagram"): 1.0,
    ("screenshot", "screenshot"): 1.0,
    ("conceptual", "photo"): 0.9,
    ("conceptual", "diagram"): 0.7,
    ("real_world", "photo"): 1.0,
    ("real_world", "screenshot"): 0.5,
    ("diagram", "screenshot"): 0.6,
    ("screenshot", "diagram"): 0.6,
}

# Phase 1 weights (no CLIP semantic score yet)
WEIGHTS = {
    "resolution": 0.35,
    "aspect_ratio": 0.25,
    "source": 0.25,
    "visual_type": 0.15,
}


def score(candidate: ImageCandidate, visual_intent: str) -> float:
    """
    Computes a composite score for an image candidate.

    Score components:
    - resolution_score: based on minimum dimension vs 500px threshold
    - aspect_ratio_score: closeness to LinkedIn ideal ratios
    - source_score: fixed weights per source
    - visual_type_score: match between visual_intent and classified image type

    Returns:
        Float in [0, 1].
    """
    image_type = classify(candidate)

    # Penalize logos heavily
    if image_type == "logo":
        return 0.0

    resolution = _resolution_score(candidate.width, candidate.height)
    aspect = _aspect_ratio_score(candidate.width, candidate.height)
    source = SOURCE_SCORES.get(candidate.source, 0.5)
    visual_type = _visual_type_score(visual_intent, image_type)

    return (
        WEIGHTS["resolution"] * resolution
        + WEIGHTS["aspect_ratio"] * aspect
        + WEIGHTS["source"] * source
        + WEIGHTS["visual_type"] * visual_type
    )


def score_all(
    candidates: list[ImageCandidate],
    visual_intent: str,
) -> list[ScoredCandidate]:
    """Scores all candidates and returns them sorted by descending score."""
    scored = [
        ScoredCandidate(candidate=c, score=score(c, visual_intent))
        for c in candidates
    ]
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored


def _resolution_score(width: int, height: int) -> float:
    if width == 0 or height == 0:
        return 0.5  # unknown — neutral score

    min_dim = min(width, height)
    if min_dim >= 500:
        return 1.0
    if min_dim >= 300:
        return 0.7
    if min_dim >= 200:
        return 0.4
    return 0.1


def _aspect_ratio_score(width: int, height: int) -> float:
    if width == 0 or height == 0:
        return 0.5  # unknown — neutral score

    ratio = width / height
    best = 0.0
    for ideal_w, ideal_h in LINKEDIN_IDEAL_RATIOS:
        ideal_ratio = ideal_w / ideal_h
        diff = abs(ratio - ideal_ratio) / ideal_ratio
        match = max(0.0, 1.0 - diff / RATIO_TOLERANCE)
        best = max(best, match)
    return best


def _visual_type_score(visual_intent: str, image_type: str) -> float:
    return VISUAL_TYPE_MATCH.get((visual_intent, image_type), 0.3)
