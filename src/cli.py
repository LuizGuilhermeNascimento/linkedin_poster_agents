from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from .core.config import OUTPUT_DIR, configure_runtime_paths, set_runtime_inputs, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_current_week() -> str:
    """Retorna label da semana ISO atual no formato YYYY-WW."""
    today = datetime.now()
    year, week, _ = today.isocalendar()
    return f"{year}-{week:02d}"


def run_pipeline(force: bool = False) -> None:
    from .services import researcher_service, writer_service

    week_label = get_current_week()
    output_dir = OUTPUT_DIR / week_label
    n_posts = settings.posts_per_week
    configure_runtime_paths(output_dir)

    if output_dir.exists() and not force:
        print(
            f"A pasta {output_dir} já existe. Use --force para regenerar.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[{week_label}] Gerando {n_posts} posts...")

    results = researcher_service.fetch_weekly_topics(n=n_posts)

    for i, result in enumerate(results, start=1):
        post_dir = output_dir / f"post_{i}"
        try:
            writer_service.create_post(
                result,
                output_dir=post_dir,
                week=week_label,
            )
            print(f'  post_{i} → "{result.title}" ✓')
        except Exception as exc:
            logger.error("Erro ao gerar post_%d: %s", i, exc)
            print(f"  post_{i} → ERRO: {exc}")

    log_summary(output_dir, n_posts)


def log_summary(output_dir: Path, n_posts: int) -> None:
    print(f"\nSalvo em: {output_dir}/")
    for i in range(1, n_posts + 1):
        post_dir = output_dir / f"post_{i}"
        if not post_dir.exists():
            continue
        files = [f.name for f in sorted(post_dir.iterdir())]
        print(f"  post_{i}/  " + "  ".join(files))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline de geração de posts LinkedIn sobre ML/DS"
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Gera os posts da semana atual",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Força regeneração mesmo que a pasta da semana já exista",
    )
    parser.add_argument(
        "--raw-results-file",
        type=Path,
        help=(
            "Usa um arquivo JSON local de raw results e pula a coleta "
            "de Tavily/arXiv"
        ),
    )
    parser.add_argument(
        "--raw-results-dir",
        type=Path,
        default=OUTPUT_DIR / "raw_results",
        help="Diretório onde os raw results coletados serão salvos",
    )

    args = parser.parse_args()

    if args.generate:
        if args.raw_results_file and not args.raw_results_file.exists():
            print(
                f"Arquivo de raw results não encontrado: {args.raw_results_file}",
                file=sys.stderr,
            )
            sys.exit(1)

        set_runtime_inputs(
            raw_results_file=args.raw_results_file,
            raw_results_dir=args.raw_results_dir,
        )
        run_pipeline(force=args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
