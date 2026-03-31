"""
LinkedIn ML/DS Content Pipeline — Orquestrador principal.

Uso:
    python main.py --generate   # Gera 3 posts e adiciona à fila
    python main.py --publish    # Publica posts agendados para hoje
    python main.py --run        # Gera + publica
    python main.py --daemon     # Modo contínuo com agendamento interno
"""
import argparse
import logging
import sys

import schedule
import time

from agents.researcher import ResearcherAgent
from agents.writer import WriterAgent
from agents.scheduler import SchedulerAgent
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def generate_posts() -> list:
    """Etapa 1+2: pesquisa tópicos e gera rascunhos."""
    researcher = ResearcherAgent()
    writer = WriterAgent()

    logger.info("Buscando tópicos da semana...")
    results = researcher.fetch_weekly_topics(n=settings.posts_per_week)
    logger.info("%d tópicos encontrados.", len(results))

    drafts = []
    for result in results:
        logger.info("Gerando post: %s", result.title)
        draft = writer.create_post(result)
        drafts.append(draft)

    return drafts


def enqueue_posts(drafts: list) -> None:
    """Etapa 3: agenda os posts gerados."""
    scheduler = SchedulerAgent()
    for draft in drafts:
        scheduler.enqueue(draft)


def publish_due_posts() -> list[str]:
    """Publica posts agendados cujo horário chegou."""
    scheduler = SchedulerAgent()
    published = scheduler.publish_due()
    logger.info("%d posts publicados.", len(published))
    return published


def log_summary(drafts: list) -> None:
    logger.info("=== Resumo da geração ===")
    for draft in drafts:
        logger.info(
            "  [%s] %s — agendado para: %s",
            draft.status,
            draft.research.title[:60],
            draft.scheduled_for,
        )


def run_pipeline() -> None:
    drafts = generate_posts()
    enqueue_posts(drafts)
    log_summary(drafts)


def run_daemon() -> None:
    """Modo daemon: roda a pipeline toda segunda/quarta/sexta e publica nos horários."""
    logger.info("Iniciando modo daemon. Ctrl+C para parar.")

    days = settings.schedule_days.split(",")
    time_str = settings.schedule_time

    for day in days:
        day = day.strip()
        getattr(schedule.every(), day).at(time_str).do(run_pipeline)
        logger.info("Agendado: toda %s às %s", day, time_str)

    while True:
        schedule.run_pending()
        time.sleep(60)


def main() -> None:
    parser = argparse.ArgumentParser(description="LinkedIn ML/DS Content Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="Gera posts e adiciona à fila")
    group.add_argument("--publish", action="store_true", help="Publica posts agendados")
    group.add_argument("--run", action="store_true", help="Gera e publica (pipeline completa)")
    group.add_argument("--daemon", action="store_true", help="Modo contínuo com agendamento")

    args = parser.parse_args()

    if args.generate:
        drafts = generate_posts()
        enqueue_posts(drafts)
        log_summary(drafts)
    elif args.publish:
        publish_due_posts()
    elif args.run:
        run_pipeline()
        publish_due_posts()
    elif args.daemon:
        run_daemon()


if __name__ == "__main__":
    main()
