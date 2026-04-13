from __future__ import annotations

import logging
from pathlib import Path

from app.config import OUTPUT_DIR, configure_runtime_paths, runtime_paths, settings

logger = logging.getLogger(__name__)


def run_weekly_pipeline(force: bool = False) -> None:
    """
    Runs the full weekly post generation pipeline.

    Skips if the week's output directory already exists (unless force=True).
    """
    import sys
    from app.config import get_current_week

    week_label = get_current_week()
    output_dir = OUTPUT_DIR / week_label
    n_posts = settings.posts_per_week
    configure_runtime_paths(output_dir)

    if output_dir.exists() and not force:
        print(
            f"Directory {output_dir} already exists. Use --force to regenerate.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[{week_label}] Generating {n_posts} posts...")

    from services import research_service
    from pipelines.linkedin_post_pipeline import run as run_post_pipeline

    results = research_service.fetch_weekly_topics(n=n_posts)

    for i, result in enumerate(results, start=1):
        post_dir = output_dir / f"post_{i}"
        try:
            run_post_pipeline(result, output_dir=post_dir, week=week_label, debug=runtime_paths.debug)
            print(f'  post_{i} → "{result.title}" ✓')
        except Exception as exc:
            logger.error("Error generating post_%d: %s", i, exc)
            print(f"  post_{i} → ERROR: {exc}")

    _log_summary(output_dir, n_posts)


def _log_summary(output_dir: Path, n_posts: int) -> None:
    print(f"\nSaved to: {output_dir}/")
    for i in range(1, n_posts + 1):
        post_dir = output_dir / f"post_{i}"
        if not post_dir.exists():
            continue
        files = [f.name for f in sorted(post_dir.iterdir())]
        print(f"  post_{i}/  " + "  ".join(files))
