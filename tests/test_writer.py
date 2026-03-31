"""Testes para o WriterAgent.

Roda com: pytest tests/test_writer.py -v
"""
from unittest.mock import MagicMock, patch

import pytest

from agents.researcher import ResearchResult
from agents.writer import PostDraft, WriterAgent


@pytest.fixture
def sample_research() -> ResearchResult:
    return ResearchResult(
        title="LoRA: Low-Rank Adaptation of LLMs",
        summary="LoRA reduz drasticamente os parâmetros treináveis em fine-tuning de LLMs.",
        source_url="https://arxiv.org/abs/2106.09685",
        source_type="paper",
        arxiv_id="2106.09685",
        suggested_angle="Como economizar GPU sem sacrificar performance",
        illustration_hint="code",
    )


@patch("agents.writer.ImageFetcher")
@patch("agents.writer.anthropic.Anthropic")
def test_create_post_returns_post_draft(
    mock_anthropic_cls,
    mock_image_fetcher_cls,
    sample_research,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("agents.writer.settings.output_queue_dir", str(tmp_path / "queue"))

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Post gerado sobre LoRA! #MachineLearning #LLM"

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_anthropic_cls.return_value.messages.create.return_value = mock_response

    mock_image_fetcher_cls.return_value.fetch_code_screenshot.return_value = (
        "/tmp/img.png",
        "https://carbon.now.sh",
        "carbon.now.sh",
    )

    agent = WriterAgent()
    draft = agent.create_post(sample_research)

    assert isinstance(draft, PostDraft)
    assert draft.status == "draft"
    assert draft.text == "Post gerado sobre LoRA! #MachineLearning #LLM"
    assert draft.research.title == sample_research.title
    assert draft.scheduled_for is None
    assert draft.id  # UUID gerado


@patch("agents.writer.ImageFetcher")
@patch("agents.writer.anthropic.Anthropic")
def test_create_post_saves_json_file(
    mock_anthropic_cls,
    mock_image_fetcher_cls,
    sample_research,
    tmp_path,
    monkeypatch,
):
    import json

    queue_dir = tmp_path / "queue"
    monkeypatch.setattr("agents.writer.settings.output_queue_dir", str(queue_dir))

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Texto do post"

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_anthropic_cls.return_value.messages.create.return_value = mock_response
    mock_image_fetcher_cls.return_value.fetch_code_screenshot.return_value = None

    agent = WriterAgent()
    draft = agent.create_post(sample_research)

    json_files = list(queue_dir.glob("*.json"))
    assert len(json_files) == 1

    data = json.loads(json_files[0].read_text())
    assert data["id"] == draft.id
    assert data["status"] == "draft"
    assert data["text"] == "Texto do post"


@patch("agents.writer.ImageFetcher")
@patch("agents.writer.anthropic.Anthropic")
def test_create_post_with_no_illustration(
    mock_anthropic_cls,
    mock_image_fetcher_cls,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("agents.writer.settings.output_queue_dir", str(tmp_path / "queue"))

    research = ResearchResult(
        title="Tendência geral em ML",
        summary="Resumo breve.",
        source_url="https://example.com",
        source_type="trend",
        arxiv_id=None,
        suggested_angle="Visão geral",
        illustration_hint="none",
    )

    mock_text_block = MagicMock()
    mock_text_block.type = "text"
    mock_text_block.text = "Texto sem imagem"

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]
    mock_anthropic_cls.return_value.messages.create.return_value = mock_response

    agent = WriterAgent()
    draft = agent.create_post(research)

    assert draft.image_path is None
    assert draft.image_url is None
    assert draft.image_credit is None


def test_post_draft_default_status():
    research = ResearchResult(
        title="T", summary="S", source_url="https://x.com",
        source_type="tool", arxiv_id=None, suggested_angle="A",
        illustration_hint="stock_photo",
    )
    draft = PostDraft(
        id="test-id",
        created_at="2024-01-01T00:00:00+00:00",
        research=research,
        text="Post text",
        image_path=None,
        image_url=None,
        image_credit=None,
        scheduled_for=None,
    )
    assert draft.status == "draft"
