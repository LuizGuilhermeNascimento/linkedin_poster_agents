import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_NS = "http://www.w3.org/2005/Atom"


class ArxivSearch:
    def search_recent(
        self,
        categories: list[str],
        max_results: int = 10,
        days_back: int = 7,
    ) -> list[dict]:
        """Busca papers recentes no arXiv nas categorias especificadas."""
        category_query = " OR ".join(f"cat:{c}" for c in categories)
        params = {
            "search_query": category_query,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        url = f"{ARXIV_API_URL}?{urlencode(params)}"
        time.sleep(3)  # boas práticas arXiv

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        return self._parse_response(response.text, days_back)

    def _parse_response(self, xml_text: str, days_back: int) -> list[dict]:
        root = ET.fromstring(xml_text)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        results: list[dict] = []

        for entry in root.findall(f"{{{ARXIV_NS}}}entry"):
            published_str = self._find_text(entry, f"{{{ARXIV_NS}}}published")
            if not published_str:
                continue

            published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            if published < cutoff:
                continue

            arxiv_id = self._extract_arxiv_id(
                self._find_text(entry, f"{{{ARXIV_NS}}}id") or ""
            )
            results.append({
                "title": self._find_text(entry, f"{{{ARXIV_NS}}}title", "").strip(),
                "summary": self._find_text(entry, f"{{{ARXIV_NS}}}summary", "").strip(),
                "url": f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "",
                "arxiv_id": arxiv_id,
                "published": published_str,
                "source": "arxiv",
                "categories": [
                    tag.get("term", "")
                    for tag in entry.findall(f"{{{ARXIV_NS}}}category")
                ],
            })

        return results

    @staticmethod
    def _find_text(element: ET.Element, tag: str, default: str = "") -> str:
        node = element.find(tag)
        return node.text if node is not None and node.text else default

    @staticmethod
    def _extract_arxiv_id(url: str) -> str | None:
        """Extrai o ID do arXiv a partir da URL ou string de ID."""
        if not url:
            return None
        # URLs como http://arxiv.org/abs/2401.12345v1
        parts = url.rstrip("/").split("/")
        raw_id = parts[-1]
        return raw_id.split("v")[0] if raw_id else None
