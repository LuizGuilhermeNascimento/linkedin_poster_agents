import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from agents.researcher import ResearchResult
from config import settings
from tools.image_fetcher import ImageFetcher

logger = logging.getLogger(__name__)


@dataclass
class PostDraft:
    id: str
    created_at: str                # ISO 8601
    research: ResearchResult
    text: str                      # Texto final do post
    image_path: str | None         # Caminho local da imagem
    image_url: str | None          # URL pública de origem
    image_credit: str | None       # Atribuição
    scheduled_for: str | None      # ISO 8601 — preenchido pelo Scheduler
    status: str = "draft"          # "draft" | "scheduled" | "published" | "failed"
    hashtags: list[str] = field(default_factory=list)


class WriterAgent:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.image_fetcher = ImageFetcher()
        self._load_prompt()

    def _load_prompt(self) -> None:
        prompt_path = Path("prompts/writer_prompt.txt")
        self.prompt_template = prompt_path.read_text(encoding="utf-8")

    def create_post(self, research: ResearchResult) -> PostDraft:
        """Gera o texto e a ilustração do post a partir de um ResearchResult."""
        text = self._generate_text(research)
        image_path, image_url, image_credit = self._fetch_illustration(research)

        draft = PostDraft(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            research=research,
            text=text,
            image_path=image_path,
            image_url=image_url,
            image_credit=image_credit,
            scheduled_for=None,
        )

        self._save_draft(draft)
        return draft

    def _generate_text(self, research: ResearchResult) -> str:
        prompt = self.prompt_template.format(
            title=research.title,
            summary=research.summary,
            suggested_angle=research.suggested_angle,
            source_url=research.source_url,
        )

        response = self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        return next(
            (block.text for block in response.content if block.type == "text"),
            "",
        )

    def _fetch_illustration(
        self, research: ResearchResult
    ) -> tuple[str | None, str | None, str | None]:
        hint = research.illustration_hint

        try:
            if hint == "paper_figure" and research.arxiv_id:
                result = self.image_fetcher.fetch_paper_figure(research.arxiv_id)
                if result:
                    return result
                hint = "repo_image"

            if hint == "repo_image":
                result = self.image_fetcher.fetch_repo_image(research.title, research.source_url)
                if result:
                    return result
                hint = "stock_photo"

            if hint == "code":
                result = self.image_fetcher.fetch_code_screenshot(research)
                if result:
                    return result
                hint = "stock_photo"

            if hint == "stock_photo":
                result = self.image_fetcher.fetch_stock_photo(research.title)
                if result:
                    return result

        except Exception:
            logger.warning("Falha ao buscar ilustração (hint=%s)", hint, exc_info=True)

        return None, None, None

    def _save_draft(self, draft: PostDraft) -> None:
        import json

        output_dir = Path(settings.output_queue_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        draft_dict = {
            "id": draft.id,
            "created_at": draft.created_at,
            "research": {
                "title": draft.research.title,
                "summary": draft.research.summary,
                "source_url": draft.research.source_url,
                "source_type": draft.research.source_type,
                "arxiv_id": draft.research.arxiv_id,
                "suggested_angle": draft.research.suggested_angle,
                "illustration_hint": draft.research.illustration_hint,
            },
            "text": draft.text,
            "image_path": draft.image_path,
            "image_url": draft.image_url,
            "image_credit": draft.image_credit,
            "scheduled_for": draft.scheduled_for,
            "status": draft.status,
        }

        output_path = output_dir / f"{draft.id}.json"
        output_path.write_text(json.dumps(draft_dict, ensure_ascii=False, indent=2))
        logger.info("Draft salvo em %s", output_path)
