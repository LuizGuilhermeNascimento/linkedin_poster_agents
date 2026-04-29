from __future__ import annotations

from pydantic import BaseModel

from .research import ResearchResult


class PostDraft(BaseModel):
    id: str
    created_at: str
    week: str
    research: ResearchResult
    text: str
    image_path: str | None
    image_url: str | None
    image_credit: str | None
    status: str = "draft"
