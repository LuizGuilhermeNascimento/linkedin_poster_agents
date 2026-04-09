from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResearchResult(BaseModel):
    title: str
    summary: str
    source_url: str
    source_type: str              # "arxiv" | "github" | "blog" | "release"
    arxiv_id: str | None
    suggested_angle: str
    illustration_hint: str        # "paper_figure" | "repo_image" | "code" | "stock_photo" | "none"
    raw_sources: list[dict[str, Any]] = Field(default_factory=list)
