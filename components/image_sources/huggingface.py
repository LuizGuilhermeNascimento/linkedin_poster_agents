from __future__ import annotations

import logging

import requests
from bs4 import BeautifulSoup

from domain.image import ImageCandidate
from components.scraping.html_parser import parse_images_from_html, HEADERS
from .base import ImageSource

logger = logging.getLogger(__name__)

HF_SEARCH_URL = "https://huggingface.co/models"
HF_BASE = "https://huggingface.co"


class HuggingFaceImageSource(ImageSource):
    """
    Fetches images from HuggingFace model cards.

    Searches models matching the query and extracts architecture
    diagrams and pipeline visuals from their model cards.
    """

    def search(self, query: str, max_results: int = 5) -> list[ImageCandidate]:
        model_slugs = self._search_models(query, limit=3)
        candidates: list[ImageCandidate] = []

        for slug in model_slugs:
            model_url = f"{HF_BASE}/{slug}"
            images = self._extract_model_card_images(model_url)
            for img in images:
                img.query_origin = query
            candidates.extend(images)
            if len(candidates) >= max_results:
                break

        return candidates[:max_results]

    def _search_models(self, query: str, limit: int = 3) -> list[str]:
        """Returns list of 'owner/model' slugs."""
        try:
            response = requests.get(
                HF_SEARCH_URL,
                params={"search": query, "sort": "downloads"},
                headers=HEADERS,
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("HuggingFace model search failed for '%s': %s", query, exc)
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        slugs: list[str] = []

        # Model cards are linked as /owner/model-name
        for link in soup.find_all("a", href=True):
            href = link["href"]
            parts = href.strip("/").split("/")
            if len(parts) == 2 and not href.startswith("#"):
                slugs.append(href.strip("/"))
                if len(slugs) >= limit:
                    break

        return slugs

    def _extract_model_card_images(self, model_url: str) -> list[ImageCandidate]:
        try:
            response = requests.get(model_url, headers=HEADERS, timeout=15)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.debug("Failed to fetch HuggingFace page %s: %s", model_url, exc)
            return []

        raw_images = parse_images_from_html(response.text, base_url=model_url, min_width=200, min_height=100)

        candidates: list[ImageCandidate] = []
        for img_data in raw_images:
            candidates.append(ImageCandidate(
                url=img_data["url"],
                source="huggingface",
                alt_text=img_data.get("alt_text", ""),
                context_text=img_data.get("context_text", "") or f"HuggingFace: {model_url}",
                width=img_data.get("width", 0),
                height=img_data.get("height", 0),
            ))

        return candidates
