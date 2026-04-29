from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    ARXIV = "arxiv"
    GITHUB = "github"
    BLOG = "blog"
    RELEASE = "release"


class VisualIntent(str, Enum):
    DIAGRAM = "diagram"
    SCREENSHOT = "screenshot"
    CONCEPTUAL = "conceptual"
    REAL_WORLD = "real_world"


class ImageSourceName(str, Enum):
    GITHUB = "github"
    HUGGINGFACE = "huggingface"
    WEB = "web"
    UNSPLASH = "unsplash"
    ARXIV = "arxiv"
