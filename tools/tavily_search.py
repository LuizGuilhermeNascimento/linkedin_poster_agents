import logging
from datetime import datetime, timedelta, timezone

import requests

from config import settings

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"


class TavilySearch:
    def __init__(self) -> None:
        self.api_key = settings.tavily_api_key

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Busca resultados na Tavily API."""
        if not self.api_key:
            logger.warning("TAVILY_API_KEY não configurada. Pulando busca.")
            return []

        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": False,
            "include_raw_content": False,
        }

        response = requests.post(TAVILY_API_URL, json=payload, timeout=30)
        response.raise_for_status()

        data = response.json()
        results = data.get("results", [])

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "source": "tavily",
                "query": query,
            }
            for r in results
        ]
