"""Testes para o ResearcherAgent.

Roda com: pytest tests/test_researcher.py -v
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from agents.researcher import ResearchResult, ResearcherAgent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_tavily_results() -> list[dict]:
    return [
        {
            "title": "New LLM benchmark beats GPT-4 on reasoning",
            "url": "https://example.com/llm-benchmark",
            "content": "Researchers released a new benchmark showing...",
            "source": "tavily",
            "query": "trending machine learning tools last 7 days",
        }
    ]


@pytest.fixture
def mock_arxiv_results() -> list[dict]:
    return [
        {
            "title": "Mixture of Experts for Efficient LLM Inference",
            "summary": "We propose a novel MoE architecture that reduces inference cost by 40%.",
            "url": "https://arxiv.org/abs/2401.99999",
            "arxiv_id": "2401.99999",
            "published": "2024-01-15T00:00:00Z",
            "source": "arxiv",
            "categories": ["cs.LG"],
        }
    ]


@pytest.fixture
def mock_llm_response() -> list[dict]:
    return [
        {
            "title": "Mixture of Experts for Efficient LLM Inference",
            "summary": "Nova arquitetura MoE reduz custo de inferência em 40%.",
            "source_url": "https://arxiv.org/abs/2401.99999",
            "source_type": "paper",
            "arxiv_id": "2401.99999",
            "suggested_angle": "Destacar impacto prático em produção",
            "illustration_hint": "paper_figure",
        }
    ]


# ---------------------------------------------------------------------------
# Testes de integração do fluxo (com mocks)
# ---------------------------------------------------------------------------

@patch("agents.researcher.TavilySearch")
@patch("agents.researcher.ArxivSearch")
@patch("agents.researcher.anthropic.Anthropic")
def test_fetch_weekly_topics_returns_research_results(
    mock_anthropic_cls,
    mock_arxiv_cls,
    mock_tavily_cls,
    mock_tavily_results,
    mock_arxiv_results,
    mock_llm_response,
):
    # Setup mocks
    mock_tavily_cls.return_value.search.return_value = mock_tavily_results
    mock_arxiv_cls.return_value.search_recent.return_value = mock_arxiv_results

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = json.dumps(mock_llm_response)

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_anthropic_cls.return_value.messages.create.return_value = mock_response

    agent = ResearcherAgent()
    results = agent.fetch_weekly_topics(n=3)

    assert len(results) == 1
    assert isinstance(results[0], ResearchResult)
    assert results[0].title == "Mixture of Experts for Efficient LLM Inference"
    assert results[0].arxiv_id == "2401.99999"
    assert results[0].source_type == "paper"
    assert results[0].illustration_hint == "paper_figure"


@patch("agents.researcher.TavilySearch")
@patch("agents.researcher.ArxivSearch")
@patch("agents.researcher.anthropic.Anthropic")
def test_fetch_weekly_topics_respects_n_limit(
    mock_anthropic_cls,
    mock_arxiv_cls,
    mock_tavily_cls,
    mock_llm_response,
):
    mock_tavily_cls.return_value.search.return_value = []
    mock_arxiv_cls.return_value.search_recent.return_value = []

    many_results = mock_llm_response * 5  # 5 resultados

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = json.dumps(many_results)

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_anthropic_cls.return_value.messages.create.return_value = mock_response

    agent = ResearcherAgent()
    results = agent.fetch_weekly_topics(n=2)

    assert len(results) == 2


@patch("agents.researcher.TavilySearch")
@patch("agents.researcher.ArxivSearch")
@patch("agents.researcher.anthropic.Anthropic")
def test_fetch_weekly_topics_handles_empty_sources(
    mock_anthropic_cls,
    mock_arxiv_cls,
    mock_tavily_cls,
):
    mock_tavily_cls.return_value.search.return_value = []
    mock_arxiv_cls.return_value.search_recent.return_value = []

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "[]"

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_anthropic_cls.return_value.messages.create.return_value = mock_response

    agent = ResearcherAgent()
    results = agent.fetch_weekly_topics(n=3)

    assert results == []


@patch("agents.researcher.TavilySearch")
@patch("agents.researcher.ArxivSearch")
@patch("agents.researcher.anthropic.Anthropic")
def test_fetch_weekly_topics_handles_invalid_llm_json(
    mock_anthropic_cls,
    mock_arxiv_cls,
    mock_tavily_cls,
    mock_tavily_results,
):
    mock_tavily_cls.return_value.search.return_value = mock_tavily_results
    mock_arxiv_cls.return_value.search_recent.return_value = []

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "este não é um JSON válido"

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_anthropic_cls.return_value.messages.create.return_value = mock_response

    agent = ResearcherAgent()
    results = agent.fetch_weekly_topics(n=3)

    assert results == []


@patch("agents.researcher.TavilySearch")
@patch("agents.researcher.ArxivSearch")
@patch("agents.researcher.anthropic.Anthropic")
def test_fetch_weekly_topics_skips_items_without_title(
    mock_anthropic_cls,
    mock_arxiv_cls,
    mock_tavily_cls,
):
    mock_tavily_cls.return_value.search.return_value = []
    mock_arxiv_cls.return_value.search_recent.return_value = []

    llm_items = [
        {"title": "Valid Topic", "summary": "...", "source_url": "https://x.com",
         "source_type": "tool", "arxiv_id": None, "suggested_angle": "...",
         "illustration_hint": "stock_photo"},
        {"summary": "sem título", "source_url": "https://y.com"},  # sem title
    ]

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = json.dumps(llm_items)

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_anthropic_cls.return_value.messages.create.return_value = mock_response

    agent = ResearcherAgent()
    results = agent.fetch_weekly_topics(n=3)

    assert len(results) == 1
    assert results[0].title == "Valid Topic"


# ---------------------------------------------------------------------------
# Testes unitários do ResearchResult
# ---------------------------------------------------------------------------

def test_research_result_fields():
    result = ResearchResult(
        title="Test Title",
        summary="Test summary in 2-3 sentences.",
        source_url="https://arxiv.org/abs/2401.00001",
        source_type="paper",
        arxiv_id="2401.00001",
        suggested_angle="Focus on practical implications",
        illustration_hint="paper_figure",
        raw_sources=[{"url": "https://arxiv.org/abs/2401.00001"}],
    )

    assert result.title == "Test Title"
    assert result.source_type == "paper"
    assert result.arxiv_id == "2401.00001"
    assert result.illustration_hint == "paper_figure"
    assert len(result.raw_sources) == 1


def test_research_result_optional_arxiv_id():
    result = ResearchResult(
        title="Some Tool",
        summary="A new ML tool.",
        source_url="https://github.com/org/tool",
        source_type="tool",
        arxiv_id=None,
        suggested_angle="Show practical demo",
        illustration_hint="repo_image",
    )

    assert result.arxiv_id is None
    assert result.raw_sources == []


def test_research_result_illustration_hint_values():
    valid_hints = ["paper_figure", "repo_image", "code", "stock_photo", "none"]
    for hint in valid_hints:
        result = ResearchResult(
            title="T",
            summary="S",
            source_url="https://x.com",
            source_type="trend",
            arxiv_id=None,
            suggested_angle="A",
            illustration_hint=hint,
        )
        assert result.illustration_hint == hint
