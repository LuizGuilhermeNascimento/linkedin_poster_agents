from __future__ import annotations

from tavily import TavilyClient

from ..core.config import settings


def search(query: str, max_results: int = 5) -> list[dict]:
    """
    Executa uma busca na Tavily e retorna resultados normalizados.

    Returns:
        Lista de dicts com keys: title, url, content, score.
    """
    client = TavilyClient(api_key=settings.tavily_api_key)
    response = client.search(
        query=query,
        search_depth="basic",
        max_results=max_results,
    )
    results = []
    for item in response.get("results", []):
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0.0),
                "source": "tavily",
            }
        )
    return results
