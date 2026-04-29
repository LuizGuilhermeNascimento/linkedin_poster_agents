from __future__ import annotations

import logging

from domain.image import ImageCandidate
from components.scraping.html_parser import fetch_page_images, extract_og_image
from components.search import tavily_client
from .base import ImageSource

logger = logging.getLogger(__name__)


class WebImageSource(ImageSource):
    """
    Fetches images via Tavily web search + HTML scraping.

    For each search result URL, extracts og:image and <figure> images.
    """

    def search(self, query: str, max_results: int = 5) -> list[ImageCandidate]:
        try:
            results = tavily_client.search(query, max_results=max_results)
        except Exception as exc:
            logger.warning("Tavily search failed for '%s': %s", query, exc)
            return []

        candidates: list[ImageCandidate] = []

        for result in results:
            url = result.get("url", "")
            if not url:
                continue

            page_images = fetch_page_images(url, min_width=200, min_height=100)
            for img_data in page_images:
                candidates.append(ImageCandidate(
                    url=img_data["url"],
                    source="web",
                    alt_text=img_data.get("alt_text", ""),
                    context_text=img_data.get("context_text", "") or result.get("title", ""),
                    query_origin=query,
                    width=img_data.get("width", 0),
                    height=img_data.get("height", 0),
                ))

            if len(candidates) >= max_results:
                break

        return candidates[:max_results]
