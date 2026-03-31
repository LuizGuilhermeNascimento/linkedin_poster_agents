import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agents.writer import PostDraft
from config import settings
from tools.linkedin_api import LinkedInAPI

logger = logging.getLogger(__name__)

SCHEDULE_DAYS_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class SchedulerAgent:
    def __init__(self) -> None:
        self.linkedin = LinkedInAPI()
        self.queue_dir = Path(settings.output_queue_dir)
        self.published_dir = Path(settings.output_published_dir)
        self.schedule_days = [
            d.strip().lower() for d in settings.schedule_days.split(",")
        ]
        self.schedule_time = settings.schedule_time

    def enqueue(self, draft: PostDraft) -> PostDraft:
        """Atribui data de publicação ao draft e salva na fila."""
        scheduled_for = self._next_available_slot()
        draft.scheduled_for = scheduled_for
        draft.status = "scheduled"
        self._update_draft_file(draft)
        logger.info("Post %s agendado para %s", draft.id, scheduled_for)
        return draft

    def publish_due(self) -> list[str]:
        """Publica todos os posts com scheduled_for <= agora. Retorna lista de IDs publicados."""
        now = datetime.now(timezone.utc)
        published_ids: list[str] = []

        for draft_path in sorted(self.queue_dir.glob("*.json")):
            draft_data = json.loads(draft_path.read_text())
            if draft_data.get("status") != "scheduled":
                continue
            scheduled_for_str = draft_data.get("scheduled_for")
            if not scheduled_for_str:
                continue

            scheduled_for = datetime.fromisoformat(scheduled_for_str)
            if scheduled_for > now:
                continue

            try:
                self._publish_draft(draft_data, draft_path)
                published_ids.append(draft_data["id"])
            except Exception:
                logger.error("Falha ao publicar post %s", draft_data.get("id"), exc_info=True)
                self._mark_failed(draft_path, draft_data)

        return published_ids

    def check_token_expiry(self) -> None:
        """Loga alerta se o token do LinkedIn vencer em menos de 10 dias."""
        # LinkedIn não retorna a data de expiração diretamente via API padrão.
        # Implementação básica: logar aviso para verificação manual periódica.
        logger.warning(
            "Verifique manualmente a expiração do token LinkedIn. "
            "Tokens duram 60 dias. Configure renovação proativa."
        )

    def _publish_draft(self, draft_data: dict, draft_path: Path) -> None:
        post_id = draft_data["id"]
        text = draft_data["text"]
        image_path = draft_data.get("image_path")

        asset_urn: str | None = None
        if image_path and Path(image_path).exists():
            asset_urn = self.linkedin.upload_image(image_path)

        self.linkedin.create_post(text=text, image_asset_urn=asset_urn)

        draft_data["status"] = "published"
        draft_data["published_at"] = datetime.now(timezone.utc).isoformat()

        published_path = self.published_dir / draft_path.name
        self.published_dir.mkdir(parents=True, exist_ok=True)
        published_path.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2))
        draft_path.unlink()

        logger.info("Post %s publicado com sucesso.", post_id)

    def _mark_failed(self, draft_path: Path, draft_data: dict) -> None:
        draft_data["status"] = "failed"
        draft_path.write_text(json.dumps(draft_data, ensure_ascii=False, indent=2))

    def _update_draft_file(self, draft: PostDraft) -> None:
        draft_path = self.queue_dir / f"{draft.id}.json"
        if not draft_path.exists():
            logger.warning("Arquivo de draft não encontrado: %s", draft_path)
            return

        data = json.loads(draft_path.read_text())
        data["scheduled_for"] = draft.scheduled_for
        data["status"] = draft.status
        draft_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _next_available_slot(self) -> str:
        """Calcula o próximo slot de publicação disponível nos dias configurados."""
        now = datetime.now(timezone.utc)
        hour, minute = (int(x) for x in self.schedule_time.split(":"))

        # Verifica slots ocupados
        occupied: set[str] = set()
        for draft_path in self.queue_dir.glob("*.json"):
            data = json.loads(draft_path.read_text())
            if data.get("scheduled_for") and data.get("status") in ("scheduled", "published"):
                occupied.add(data["scheduled_for"][:10])  # só a data

        candidate = now
        for _ in range(30):  # busca até 30 dias à frente
            candidate = candidate + timedelta(days=1)
            day_name = candidate.strftime("%A").lower()
            if day_name not in self.schedule_days:
                continue
            date_str = candidate.strftime("%Y-%m-%d")
            if date_str in occupied:
                continue
            scheduled_dt = candidate.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            return scheduled_dt.isoformat()

        # Fallback: 7 dias à frente
        fallback = now + timedelta(days=7)
        return fallback.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()
