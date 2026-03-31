import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from config import settings
from tools.arxiv_search import ArxivSearch
from tools.tavily_search import TavilySearch

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    title: str
    summary: str                  # 2-3 frases explicando o tópico
    source_url: str
    source_type: str              # "paper" | "tool" | "trend" | "tutorial"
    arxiv_id: str | None          # Ex: "2401.12345" — se for paper
    suggested_angle: str          # Ângulo editorial sugerido pelo LLM
    illustration_hint: str        # "code" | "paper_figure" | "repo_image" | "stock_photo" | "none"
    raw_sources: list[dict] = field(default_factory=list)


class ResearcherAgent:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.tavily = TavilySearch()
        self.arxiv = ArxivSearch()
        self._load_prompt()

    def _load_prompt(self) -> None:
        prompt_path = Path("prompts/researcher_prompt.txt")
        self.prompt_template = prompt_path.read_text(encoding="utf-8")

    def fetch_weekly_topics(self, n: int = 3) -> list[ResearchResult]:
        """Busca e ranqueia os tópicos mais relevantes da semana."""
        raw_results = self._collect_raw_results()
        ranked = self._rank_with_llm(raw_results)
        return ranked[:n]

    def _collect_raw_results(self) -> list[dict]:
        results: list[dict] = []

        tavily_queries = [
            "trending machine learning tools last 7 days",
            "new AI research papers this week",
            "data science techniques trending",
        ]
        for query in tavily_queries:
            try:
                hits = self.tavily.search(query, max_results=settings.tavily_max_results)
                results.extend(hits)
            except Exception:
                logger.warning("Tavily search falhou para query: %s", query, exc_info=True)

        try:
            papers = self.arxiv.search_recent(
                categories=["cs.LG", "cs.AI", "stat.ML"],
                max_results=settings.arxiv_max_results,
            )
            results.extend(papers)
        except Exception:
            logger.warning("Busca arXiv falhou", exc_info=True)

        return results

    def _rank_with_llm(self, raw_results: list[dict]) -> list[ResearchResult]:
        if not raw_results:
            logger.warning("Nenhum resultado bruto para ranquear.")
            return []

        prompt = self.prompt_template.format(raw_results=json.dumps(raw_results, ensure_ascii=False))

        response = self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

        text_content = next(
            (block.text for block in response.content if block.type == "text"),
            "[]",
        )

        try:
            items = json.loads(text_content)
        except json.JSONDecodeError:
            logger.error("LLM retornou JSON inválido: %s", text_content[:500])
            return []

        return [
            ResearchResult(
                title=item.get("title", ""),
                summary=item.get("summary", ""),
                source_url=item.get("source_url", ""),
                source_type=item.get("source_type", "trend"),
                arxiv_id=item.get("arxiv_id"),
                suggested_angle=item.get("suggested_angle", ""),
                illustration_hint=item.get("illustration_hint", "stock_photo"),
                raw_sources=raw_results,
            )
            for item in items
            if item.get("title")
        ]
