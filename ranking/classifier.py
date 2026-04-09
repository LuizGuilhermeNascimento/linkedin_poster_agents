from __future__ import annotations

import re

from domain.image import ImageCandidate

# Keywords that suggest each image type
DIAGRAM_KEYWORDS = re.compile(
    r"(diagram|architecture|workflow|pipeline|flowchart|graph|schema|"
    r"overview|structure|layers|components|arch\b)",
    re.IGNORECASE,
)
SCREENSHOT_KEYWORDS = re.compile(
    r"(screenshot|demo|example|output|result|interface|ui|cli|terminal|"
    r"notebook|colab|usage|preview)",
    re.IGNORECASE,
)
PHOTO_KEYWORDS = re.compile(
    r"(photo|photograph|image|picture|scene|landscape|portrait|background)",
    re.IGNORECASE,
)
LOGO_KEYWORDS = re.compile(
    r"(logo|icon|badge|avatar|profile|brand|mark\.svg|\.ico)",
    re.IGNORECASE,
)


def classify(candidate: ImageCandidate) -> str:
    """
    Heuristic classification of an image candidate.

    Uses URL, alt_text, and context_text to determine image type.

    Returns:
        One of: "diagram" | "screenshot" | "photo" | "logo" | "unknown"
    """
    text = " ".join([
        candidate.url,
        candidate.alt_text,
        candidate.context_text,
    ])

    if LOGO_KEYWORDS.search(text):
        return "logo"
    if DIAGRAM_KEYWORDS.search(text):
        return "diagram"
    if SCREENSHOT_KEYWORDS.search(text):
        return "screenshot"
    if PHOTO_KEYWORDS.search(text):
        return "photo"

    # Source-based fallback
    if candidate.source in ("github", "huggingface"):
        return "diagram"
    if candidate.source == "unsplash":
        return "photo"

    return "unknown"
