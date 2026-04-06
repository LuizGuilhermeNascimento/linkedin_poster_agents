from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResearchResult(BaseModel):
    title: str
    summary: str                  # 2-3 frases explicando o tópico
    source_url: str
    source_type: str              # "paper" | "tool" | "trend" | "tutorial"
    arxiv_id: str | None          # Ex: "2401.12345" — se for paper
    suggested_angle: str          # Ângulo editorial sugerido pelo LLM
    illustration_hint: str        # "code" | "paper_figure" | "repo_image" | "stock_photo" | "none"
    raw_sources: list[dict[str, Any]] = Field(default_factory=list)


class PostDraft(BaseModel):
    id: str                       # UUID gerado na criação
    created_at: str               # ISO 8601
    week: str                     # Ex: "2025-28" (ano-semana ISO)
    research: ResearchResult
    text: str                     # Texto final do post
    image_path: str | None        # Caminho relativo: "output/2025-28/post_1/image.png"
    image_url: str | None         # URL pública de origem (paper, repo, Unsplash)
    image_credit: str | None      # Atribuição (ex: "Unsplash / @username" ou "arXiv:2401.12345")
    status: str = "draft"         # "draft" (único valor — publicação é manual)
