from __future__ import annotations

import time
import xml.etree.ElementTree as ET

import requests

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_NS = "http://www.w3.org/2005/Atom"


def search_recent_papers(
    categories: list[str] | None = None,
    max_results: int = 10,
) -> list[dict]:
    """
    Busca papers recentes no arXiv nas categorias informadas.

    Returns:
        Lista de dicts com keys: title, url, arxiv_id, summary, authors, published.
    """
    if categories is None:
        categories = ["cs.LG", "cs.AI", "stat.ML"]

    category_query = " OR ".join(f"cat:{c}" for c in categories)
    params = {
        "search_query": category_query,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }

    time.sleep(3)  # boas práticas arXiv
    response = requests.get(ARXIV_API_URL, params=params, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    results = []

    for entry in root.findall(f"{{{ARXIV_NS}}}entry"):
        arxiv_id = _extract_arxiv_id(entry)
        results.append(
            {
                "title": _get_text(entry, f"{{{ARXIV_NS}}}title"),
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "arxiv_id": arxiv_id,
                "summary": _get_text(entry, f"{{{ARXIV_NS}}}summary"),
                "authors": _extract_authors(entry),
                "published": _get_text(entry, f"{{{ARXIV_NS}}}published"),
                "source": "arxiv",
            }
        )

    return results


def _get_text(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _extract_arxiv_id(entry: ET.Element) -> str:
    id_url = _get_text(entry, f"{{{ARXIV_NS}}}id")
    return id_url.split("/abs/")[-1].split("v")[0]


def _extract_authors(entry: ET.Element) -> list[str]:
    authors = []
    for author in entry.findall(f"{{{ARXIV_NS}}}author"):
        name = _get_text(author, f"{{{ARXIV_NS}}}name")
        if name:
            authors.append(name)
    return authors[:5]
