from __future__ import annotations

import logging

import requests

from app.config import settings
from domain.image import ImageCandidate
from .base import ImageSource

logger = logging.getLogger(__name__)


class UnsplashImageSource(ImageSource):
    """
    Fetches images from Unsplash.

    Used as a last resort for conceptual and real_world visual intents.
    Requires UNSPLASH_ACCESS_KEY to be configured.
    """

    def search(self, query: str, max_results: int = 5) -> list[ImageCandidate]:
        if not settings.unsplash_access_key:
            logger.debug("UNSPLASH_ACCESS_KEY not configured — skipping Unsplash.")
            return []

        try:
            response = requests.get(
                "https://api.unsplash.com/search/photos",
                params={
                    "query": query,
                    "per_page": max_results,
                    "orientation": "landscape",
                    "client_id": settings.unsplash_access_key,
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            logger.warning("Unsplash search failed for '%s': %s", query, exc)
            return []

        candidates: list[ImageCandidate] = []
        for photo in data.get("results", []):
            url = photo.get("urls", {}).get("regular", "")
            if not url:
                continue
            username = photo.get("user", {}).get("username", "unknown")
            width = photo.get("width", 0)
            height = photo.get("height", 0)
            candidates.append(ImageCandidate(
                url=url,
                source="unsplash",
                alt_text=photo.get("alt_description", "") or photo.get("description", ""),
                context_text=f"Unsplash / @{username}",
                query_origin=query,
                width=width,
                height=height,
            ))

        return candidates
