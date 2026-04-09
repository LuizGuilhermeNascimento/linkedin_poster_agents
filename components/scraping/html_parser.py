from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "linkedin-ml-pipeline/1.0 (educational project)"}

# Patterns that indicate non-content images (badges, icons, logos)
BADGE_PATTERNS = re.compile(
    r"(badge|shield|travis|codecov|license|version|build|status|npm|pypi|"
    r"logo|icon|favicon|avatar|profile|button|banner\.svg)",
    re.IGNORECASE,
)


def fetch_page_images(
    url: str,
    min_width: int = 200,
    min_height: int = 200,
    timeout: int = 15,
) -> list[dict]:
    """
    Fetches a page and extracts image candidates.

    Returns:
        List of dicts with keys: url, alt_text, width, height, context_text.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return []

    return parse_images_from_html(response.text, base_url=url, min_width=min_width, min_height=min_height)


def parse_images_from_html(
    html: str,
    base_url: str = "",
    min_width: int = 0,
    min_height: int = 0,
) -> list[dict]:
    """
    Parses image candidates from HTML, returning metadata without downloading.

    Extracts:
    - og:image meta tag (highest priority)
    - <figure> images
    - <img> tags with meaningful alt text or size attributes
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[dict] = []

    # og:image — usually the best representative image
    og_tag = soup.find("meta", property="og:image")
    if og_tag and og_tag.get("content"):
        og_url = _make_absolute(og_tag["content"], base_url)
        if og_url and not _is_badge(og_url):
            candidates.append({
                "url": og_url,
                "alt_text": soup.title.string if soup.title else "",
                "width": 0,
                "height": 0,
                "context_text": "og:image",
            })

    # <figure> images — typically diagrams/illustrations in articles
    for figure in soup.find_all("figure"):
        img = figure.find("img")
        if img and img.get("src"):
            img_url = _make_absolute(img["src"], base_url)
            if not img_url or _is_badge(img_url):
                continue
            caption = figure.find("figcaption")
            context = caption.get_text(strip=True) if caption else ""
            width = _parse_int(img.get("width", "0"))
            height = _parse_int(img.get("height", "0"))
            if (width == 0 or width >= min_width) and (height == 0 or height >= min_height):
                candidates.append({
                    "url": img_url,
                    "alt_text": img.get("alt", ""),
                    "width": width,
                    "height": height,
                    "context_text": context,
                })

    # Regular <img> tags with meaningful attributes
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src:
            continue
        img_url = _make_absolute(src, base_url)
        if not img_url or _is_badge(img_url):
            continue

        alt = img.get("alt", "")
        width = _parse_int(img.get("width", "0"))
        height = _parse_int(img.get("height", "0"))

        if width > 0 and width < min_width:
            continue
        if height > 0 and height < min_height:
            continue

        # Skip images that are likely decorative (no alt, no size info, badge-like name)
        if not alt and width == 0 and height == 0:
            continue

        context = _get_surrounding_text(img)
        candidates.append({
            "url": img_url,
            "alt_text": alt,
            "width": width,
            "height": height,
            "context_text": context,
        })

    return candidates


def extract_og_image(url: str, timeout: int = 15) -> str | None:
    """Returns the og:image URL for a page, or None."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        og_tag = soup.find("meta", property="og:image")
        if og_tag and og_tag.get("content"):
            return og_tag["content"]
    except requests.RequestException as exc:
        logger.debug("Failed to fetch og:image from %s: %s", url, exc)
    return None


def _make_absolute(url: str, base_url: str) -> str | None:
    if not url or url.startswith("data:"):
        return None
    if url.startswith("//"):
        scheme = urlparse(base_url).scheme or "https"
        return f"{scheme}:{url}"
    if url.startswith("http"):
        return url
    if base_url:
        return urljoin(base_url, url)
    return None


def _is_badge(url: str) -> bool:
    return bool(BADGE_PATTERNS.search(url))


def _parse_int(value: str) -> int:
    try:
        return int(value.replace("px", "").strip())
    except (ValueError, AttributeError):
        return 0


def _get_surrounding_text(img_tag) -> str:
    """Gets a short snippet of text near an image for context scoring."""
    parent = img_tag.parent
    if parent:
        return parent.get_text(strip=True)[:200]
    return ""
