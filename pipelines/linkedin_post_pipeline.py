from __future__ import annotations

import logging
from pathlib import Path

from domain.post import PostDraft
from domain.research import ResearchResult

logger = logging.getLogger(__name__)


def run(
    result: ResearchResult,
    output_dir: Path,
    week: str,
    debug: bool = False,
) -> PostDraft:
    """
    Full LinkedIn post pipeline: write text + fetch image → PostDraft.

    Delegates to writer_service which orchestrates text generation and image fetching.
    """
    from services import writer_service

    return writer_service.create_post(result, output_dir=output_dir, week=week, debug=debug)
