from __future__ import annotations

import logging
from pathlib import Path

from domain.image import ImageResult
from domain.research import ResearchResult
from pipelines import image_pipeline

logger = logging.getLogger(__name__)


def get_best_image(research: ResearchResult, output_dir: Path, debug: bool = False) -> ImageResult:
    """
    Fetches the best image for a research result.

    Orchestrates the full image pipeline:
    1. Visual intent determination
    2. Multi-query generation
    3. Parallel multi-source fetching
    4. Scoring and selection
    5. Post-processing (resize for LinkedIn)

    Falls back to code screenshot for "code" illustration_hint,
    delegating that path to the writer_service.

    Returns:
        ImageResult — image_path is None if no suitable image was found.
    """
    output_path = output_dir / "image.png"
    return image_pipeline.run(research, output_path, debug=debug)
