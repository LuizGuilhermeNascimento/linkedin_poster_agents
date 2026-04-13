"""Entry point — run with: python main.py --generate"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.config import OUTPUT_DIR, set_runtime_inputs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LinkedIn post generation pipeline for ML/DS"
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate posts for the current week",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if the week's directory already exists",
    )
    parser.add_argument(
        "--raw-results-file",
        type=Path,
        help="Use a local JSON file of raw results, skipping Tavily/arXiv collection",
    )
    parser.add_argument(
        "--raw-results-dir",
        type=Path,
        default=OUTPUT_DIR / "raw_results",
        help="Directory where collected raw results will be saved",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode: save all ranked images/figures",
    )

    args = parser.parse_args()

    if args.generate:
        if args.raw_results_file and not args.raw_results_file.exists():
            print(
                f"Raw results file not found: {args.raw_results_file}",
                file=sys.stderr,
            )
            sys.exit(1)

        set_runtime_inputs(
            raw_results_file=args.raw_results_file,
            raw_results_dir=args.raw_results_dir,
            debug=args.debug,
        )

        from app.pipeline import run_weekly_pipeline
        run_weekly_pipeline(force=args.force)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
