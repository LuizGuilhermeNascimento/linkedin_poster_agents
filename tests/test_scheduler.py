"""Testes para o SchedulerAgent.

Roda com: pytest tests/test_scheduler.py -v
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.researcher import ResearchResult
from agents.scheduler import SchedulerAgent
from agents.writer import PostDraft


@pytest.fixture
def sample_draft(tmp_path) -> PostDraft:
    research = ResearchResult(
        title="Test Topic",
        summary="Summary.",
        source_url="https://arxiv.org/abs/2401.00001",
        source_type="paper",
        arxiv_id="2401.00001",
        suggested_angle="angle",
        illustration_hint="paper_figure",
    )
    draft = PostDraft(
        id="draft-001",
        created_at="2024-01-01T00:00:00+00:00",
        research=research,
        text="Post text here",
        image_path=None,
        image_url=None,
        image_credit=None,
        scheduled_for=None,
    )
    return draft


@pytest.fixture
def scheduler_with_tmp(tmp_path, monkeypatch) -> SchedulerAgent:
    queue_dir = tmp_path / "queue"
    published_dir = tmp_path / "published"
    queue_dir.mkdir()
    published_dir.mkdir()
    monkeypatch.setattr("agents.scheduler.settings.output_queue_dir", str(queue_dir))
    monkeypatch.setattr("agents.scheduler.settings.output_published_dir", str(published_dir))
    monkeypatch.setattr("agents.scheduler.settings.schedule_days", "monday,wednesday,friday")
    monkeypatch.setattr("agents.scheduler.settings.schedule_time", "09:00")
    return SchedulerAgent()


@patch("agents.scheduler.LinkedInAPI")
def test_enqueue_assigns_scheduled_for(
    mock_linkedin_cls,
    scheduler_with_tmp,
    sample_draft,
    tmp_path,
):
    # Salva o arquivo de draft antes de enfileirar
    queue_dir = tmp_path / "queue"
    draft_path = queue_dir / f"{sample_draft.id}.json"
    draft_path.write_text(json.dumps({
        "id": sample_draft.id,
        "status": "draft",
        "scheduled_for": None,
        "text": sample_draft.text,
    }))

    result = scheduler_with_tmp.enqueue(sample_draft)

    assert result.status == "scheduled"
    assert result.scheduled_for is not None

    # Verifica que o arquivo foi atualizado
    data = json.loads(draft_path.read_text())
    assert data["status"] == "scheduled"
    assert data["scheduled_for"] is not None


@patch("agents.scheduler.LinkedInAPI")
def test_enqueue_respects_schedule_days(
    mock_linkedin_cls,
    scheduler_with_tmp,
    sample_draft,
    tmp_path,
):
    queue_dir = tmp_path / "queue"
    draft_path = queue_dir / f"{sample_draft.id}.json"
    draft_path.write_text(json.dumps({
        "id": sample_draft.id, "status": "draft", "scheduled_for": None
    }))

    result = scheduler_with_tmp.enqueue(sample_draft)

    scheduled_dt = datetime.fromisoformat(result.scheduled_for)
    day_name = scheduled_dt.strftime("%A").lower()
    assert day_name in ("monday", "wednesday", "friday")


@patch("agents.scheduler.LinkedInAPI")
def test_publish_due_moves_to_published(
    mock_linkedin_cls,
    scheduler_with_tmp,
    tmp_path,
    monkeypatch,
):
    mock_linkedin_cls.return_value.create_post.return_value = "urn:li:ugcPost:123"
    mock_linkedin_cls.return_value.upload_image.return_value = None

    queue_dir = tmp_path / "queue"
    published_dir = tmp_path / "published"

    # Draft com scheduled_for no passado
    past_time = "2020-01-01T09:00:00+00:00"
    draft_data = {
        "id": "draft-past",
        "status": "scheduled",
        "scheduled_for": past_time,
        "text": "Post content",
        "image_path": None,
    }
    (queue_dir / "draft-past.json").write_text(json.dumps(draft_data))

    published = scheduler_with_tmp.publish_due()

    assert "draft-past" in published
    assert not (queue_dir / "draft-past.json").exists()
    assert (published_dir / "draft-past.json").exists()

    published_data = json.loads((published_dir / "draft-past.json").read_text())
    assert published_data["status"] == "published"


@patch("agents.scheduler.LinkedInAPI")
def test_publish_due_skips_future_posts(
    mock_linkedin_cls,
    scheduler_with_tmp,
    tmp_path,
):
    queue_dir = tmp_path / "queue"

    future_time = "2099-01-01T09:00:00+00:00"
    draft_data = {
        "id": "draft-future",
        "status": "scheduled",
        "scheduled_for": future_time,
        "text": "Future post",
        "image_path": None,
    }
    (queue_dir / "draft-future.json").write_text(json.dumps(draft_data))

    published = scheduler_with_tmp.publish_due()

    assert "draft-future" not in published
    assert (queue_dir / "draft-future.json").exists()


@patch("agents.scheduler.LinkedInAPI")
def test_publish_due_marks_failed_on_error(
    mock_linkedin_cls,
    scheduler_with_tmp,
    tmp_path,
):
    mock_linkedin_cls.return_value.create_post.side_effect = Exception("API down")

    queue_dir = tmp_path / "queue"
    past_time = "2020-01-01T09:00:00+00:00"
    draft_data = {
        "id": "draft-fail",
        "status": "scheduled",
        "scheduled_for": past_time,
        "text": "Will fail",
        "image_path": None,
    }
    (queue_dir / "draft-fail.json").write_text(json.dumps(draft_data))

    published = scheduler_with_tmp.publish_due()

    assert "draft-fail" not in published
    data = json.loads((queue_dir / "draft-fail.json").read_text())
    assert data["status"] == "failed"


@patch("agents.scheduler.LinkedInAPI")
def test_next_available_slot_avoids_occupied_dates(
    mock_linkedin_cls,
    scheduler_with_tmp,
    tmp_path,
):
    """Dois enfileiramentos consecutivos devem ter datas diferentes."""
    queue_dir = tmp_path / "queue"

    # Enfileira o primeiro draft
    d1 = PostDraft(
        id="d1", created_at="2024-01-01T00:00:00+00:00",
        research=MagicMock(), text="T1", image_path=None,
        image_url=None, image_credit=None, scheduled_for=None,
    )
    (queue_dir / "d1.json").write_text(json.dumps(
        {"id": "d1", "status": "draft", "scheduled_for": None}
    ))
    scheduler_with_tmp.enqueue(d1)
    date1 = d1.scheduled_for[:10]

    # Enfileira o segundo draft
    d2 = PostDraft(
        id="d2", created_at="2024-01-01T00:00:00+00:00",
        research=MagicMock(), text="T2", image_path=None,
        image_url=None, image_credit=None, scheduled_for=None,
    )
    (queue_dir / "d2.json").write_text(json.dumps(
        {"id": "d2", "status": "draft", "scheduled_for": None}
    ))
    scheduler_with_tmp.enqueue(d2)
    date2 = d2.scheduled_for[:10]

    assert date1 != date2
