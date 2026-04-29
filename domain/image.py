from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ArxivFigure:
    image_data: bytes
    width: int
    height: int
    page_number: int    # 1-indexed
    figure_index: int   # sequential 0-indexed across the PDF
    caption: str = ""   # extracted caption text (may be empty)
    confidence: float = 1.0   # reconstruction confidence score [0, 1]
    element_count: int = 1    # number of raw image XObjects merged into this figure


@dataclass
class ImageCandidate:
    url: str
    source: str          # "github" | "huggingface" | "web" | "unsplash" | "arxiv"
    alt_text: str = ""
    context_text: str = ""
    query_origin: str = ""
    width: int = 0       # 0 means unknown (not yet downloaded)
    height: int = 0


@dataclass
class VisualIntentOutput:
    visual_intent: str   # "diagram" | "screenshot" | "conceptual" | "real_world"
    entities: list[str] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    avoid_terms: list[str] = field(default_factory=list)


@dataclass
class ScoredCandidate:
    candidate: ImageCandidate
    score: float
    local_path: Path | None = None


@dataclass
class ImageResult:
    image_path: Path | None
    image_url: str | None
    source: str | None
    score: float
    credit: str | None
    candidates: list[ScoredCandidate] = field(default_factory=list)
