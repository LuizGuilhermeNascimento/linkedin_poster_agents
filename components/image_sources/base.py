from __future__ import annotations

from abc import ABC, abstractmethod

from domain.image import ImageCandidate


class ImageSource(ABC):
    """Base class for all image sources."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[ImageCandidate]:
        """
        Searches for image candidates matching the query.

        Returns:
            List of ImageCandidate with populated metadata.
            width/height may be 0 if unknown before download.
        """
        ...
