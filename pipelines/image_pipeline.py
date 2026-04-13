from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from pathlib import Path

from domain.image import ImageCandidate, ImageResult, ScoredCandidate, VisualIntentOutput
from domain.research import ResearchResult
from components.image_sources.base import ImageSource
from components.image_sources.github import GitHubImageSource
from components.image_sources.huggingface import HuggingFaceImageSource
from components.image_sources.web import WebImageSource
from components.image_sources.unsplash import UnsplashImageSource
from components.scraping.image_extractor import (
    extract_figures_with_captions,
    download_image,
    get_image_dimensions,
)
from ranking import scorer
from ranking import figure_ranker
from utils.image_utils import postprocess_image

logger = logging.getLogger(__name__)

# Per-source and global timeouts (seconds)
SOURCE_TIMEOUT = 10
MIN_SCORE_THRESHOLD = 0.3


def run(research: ResearchResult, output_path: Path, debug: bool = False) -> ImageResult:
    """
    Full image pipeline: visual intent → queries → parallel fetch → score → select → save.

    Tries arXiv PDF extraction first if source is arxiv, then falls back to
    multi-source fetching.

    Returns:
        ImageResult with image_path if successful, or all-None fields on failure.
    """
    # Fast path: arXiv paper — extract and rank figures from PDF
    if research.arxiv_id:
        arxiv_result = _select_arxiv_figure(research, output_path, debug=debug)
        if arxiv_result is not None:
            return arxiv_result

    visual_intent_output = _build_visual_intent(research)
    queries = _generate_queries(visual_intent_output)

    logger.info(
        "Image pipeline: visual_intent=%s, queries=%d",
        visual_intent_output.visual_intent,
        len(queries),
    )

    candidates = _fetch_candidates_parallel(
        queries,
        visual_intent=visual_intent_output.visual_intent,
    )

    if not candidates:
        logger.warning("No image candidates found.")
        return ImageResult(image_path=None, image_url=None, source=None, score=0.0, credit=None)

    # First-pass scoring with available metadata (no dimensions yet)
    scored = scorer.score_all(candidates, visual_intent_output.visual_intent)

    # Download top candidates to get actual dimensions and re-score
    best, final_scored = _select_and_download(scored[:8], visual_intent_output.visual_intent, output_path)

    if debug and final_scored:
        _save_ranked_candidate_images(final_scored, output_path.parent / "images_rank")

    if best is None:
        logger.warning("No suitable image found above threshold %.1f", MIN_SCORE_THRESHOLD)
        return ImageResult(image_path=None, image_url=None, source=None, score=0.0, credit=None, candidates=final_scored)

    postprocess_image(output_path)
    logger.info("Image selected: source=%s, score=%.2f, url=%s", best.candidate.source, best.score, best.candidate.url)

    credit = _build_credit(best.candidate)
    return ImageResult(
        image_path=output_path,
        image_url=best.candidate.url,
        source=best.candidate.source,
        score=best.score,
        credit=credit,
        candidates=final_scored,
    )


def _select_arxiv_figure(
    research: ResearchResult,
    output_path: Path,
    debug: bool = False,
) -> ImageResult | None:
    """
    Extracts figures from the arXiv PDF, ranks them by relevance to the post
    context, and saves the best one.

    Returns:
        ImageResult if a suitable figure was found and saved, None otherwise.
    """
    figures = extract_figures_with_captions(research.arxiv_id)
    if not figures:
        return None

    best_figure, scored = figure_ranker.rank_and_select(
        figures,
        post_summary=research.summary,
        post_angle=research.suggested_angle,
    )

    if debug and scored:
        _save_ranked_arxiv_figures(scored, output_path.parent / "images_rank")

    if best_figure is None:
        logger.warning(
            "No ranked figure selected from arXiv %s — falling back to other sources",
            research.arxiv_id,
        )
        return None

    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(best_figure.image_data)).convert("RGB")
        img.save(output_path, "PNG")
    except Exception as exc:
        logger.warning("Failed to save ranked arXiv figure: %s", exc)
        return None

    postprocess_image(output_path)
    logger.info(
        "arXiv figure saved: page=%d idx=%d caption=%r",
        best_figure.page_number, best_figure.figure_index, best_figure.caption[:80],
    )
    return ImageResult(
        image_path=output_path,
        image_url=f"https://arxiv.org/pdf/{research.arxiv_id}",
        source="arxiv",
        score=1.0,
        credit=f"arXiv:{research.arxiv_id}",
    )


def _build_visual_intent(research: ResearchResult) -> VisualIntentOutput:
    """
    Heuristic visual intent builder (Phase 1 — no LLM call).

    Determines visual_intent from source_type and title keywords,
    and extracts entities from the title.
    """
    source_type = research.source_type.lower()
    title_lower = research.title.lower()

    if source_type == "arxiv" or any(kw in title_lower for kw in ("paper", "model", "algorithm", "framework", "benchmark")):
        visual_intent = "diagram"
    elif source_type in ("github", "release") or any(kw in title_lower for kw in ("library", "tool", "sdk", "api", "package")):
        visual_intent = "screenshot"
    elif any(kw in title_lower for kw in ("business", "productivity", "impact", "enterprise", "industry")):
        visual_intent = "real_world"
    else:
        visual_intent = "conceptual"

    # Extract entities: capitalize meaningful words from title
    entities = [word for word in research.title.split() if len(word) > 3 and word[0].isupper()][:3]
    if not entities:
        entities = research.title.split()[:2]

    search_terms = [research.title] + entities[:2]
    avoid_terms = ["logo", "icon", "badge", "avatar"]

    return VisualIntentOutput(
        visual_intent=visual_intent,
        entities=entities,
        search_terms=search_terms,
        avoid_terms=avoid_terms,
    )


def _generate_queries(intent: VisualIntentOutput) -> list[str]:
    """
    Generates 4–8 complementary search queries from visual intent.

    Varies visual type (diagram/workflow/architecture) and source (github/blog).
    """
    queries: list[str] = []
    entities = intent.entities or intent.search_terms[:1]
    entity = entities[0] if entities else "machine learning"
    additional = entities[1] if len(entities) > 1 else ""

    visual_terms_by_intent = {
        "diagram": ["architecture diagram", "workflow diagram", "system overview", "github readme diagram"],
        "screenshot": ["screenshot", "demo example", "github readme", "tutorial example"],
        "conceptual": ["concept illustration", "visual explanation", "overview diagram", "explainer"],
        "real_world": ["real world example", "use case", "application", "production example"],
    }

    visual_terms = visual_terms_by_intent.get(intent.visual_intent, ["diagram", "example"])

    for term in visual_terms:
        queries.append(f"{entity} {term}")

    if additional:
        queries.append(f"{entity} {additional} overview")
        queries.append(f"{entity} {additional} site:github.com")

    queries.append(f"{entity} site:github.com")
    queries.append(f"{entity} site:huggingface.co")

    return queries[:8]


def _fetch_candidates_parallel(
    queries: list[str],
    visual_intent: str,
) -> list[ImageCandidate]:
    """
    Runs all sources in parallel for each query.

    Sources are prioritized: GitHub > HuggingFace > Web > Unsplash.
    Unsplash is only used for conceptual/real_world intents.
    """
    sources: list[ImageSource] = [
        GitHubImageSource(),
        HuggingFaceImageSource(),
        WebImageSource(),
    ]
    if visual_intent in ("conceptual", "real_world"):
        sources.append(UnsplashImageSource())

    all_candidates: list[ImageCandidate] = []
    tasks: list[tuple[ImageSource, str]] = [
        (source, query)
        for query in queries[:4]  # limit queries to avoid too many requests
        for source in sources
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_safe_search, source, query): (source, query)
            for source, query in tasks
        }
        for future in as_completed(futures, timeout=SOURCE_TIMEOUT * 2):
            try:
                results = future.result(timeout=SOURCE_TIMEOUT)
                all_candidates.extend(results)
            except TimeoutError:
                source, query = futures[future]
                logger.warning("Timeout fetching from %s for '%s'", type(source).__name__, query)
            except Exception as exc:
                source, query = futures[future]
                logger.warning("Error fetching from %s: %s", type(source).__name__, exc)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    unique: list[ImageCandidate] = []
    for c in all_candidates:
        if c.url not in seen_urls:
            seen_urls.add(c.url)
            unique.append(c)

    return unique


def _safe_search(source: ImageSource, query: str) -> list[ImageCandidate]:
    try:
        return source.search(query, max_results=3)
    except Exception as exc:
        logger.debug("Source %s failed for '%s': %s", type(source).__name__, query, exc)
        return []


def _select_and_download(
    scored_candidates: list[ScoredCandidate],
    visual_intent: str,
    output_path: Path,
) -> tuple[ScoredCandidate | None, list[ScoredCandidate]]:
    """
    Downloads top candidates, refreshes scores with real dimensions, returns
    the best ScoredCandidate and the full re-scored list.
    """
    final_scored: list[ScoredCandidate] = []

    for scored in scored_candidates:
        candidate = scored.candidate

        # Get actual dimensions if unknown
        if candidate.width == 0 or candidate.height == 0:
            w, h = get_image_dimensions(candidate.url)
            candidate.width = w
            candidate.height = h

        final_score = scorer.score(candidate, visual_intent)
        final_scored.append(ScoredCandidate(candidate=candidate, score=final_score))

    final_scored.sort(key=lambda x: x.score, reverse=True)

    for scored in final_scored:
        if scored.score < MIN_SCORE_THRESHOLD:
            break
        if download_image(scored.candidate.url, output_path):
            return scored, final_scored

    return None, final_scored


def _save_ranked_candidate_images(scored_candidates: list[ScoredCandidate], rank_dir: Path) -> None:
    """Saves all ranked external candidates as PNG files for debugging."""
    rank_dir.mkdir(parents=True, exist_ok=True)

    for i, scored in enumerate(scored_candidates, start=1):
        target = rank_dir / f"top_{i:02d}.png"
        try:
            if not download_image(scored.candidate.url, target):
                logger.debug("Skipping debug ranked image #%d: %s", i, scored.candidate.url)
        except Exception as exc:
            logger.debug("Failed to save debug ranked image #%d (%s): %s", i, scored.candidate.url, exc)


def _save_ranked_arxiv_figures(scored_figures: list[object], rank_dir: Path) -> None:
    """Saves all ranked arXiv figures as PNG files for debugging."""
    if not scored_figures:
        return

    rank_dir.mkdir(parents=True, exist_ok=True)
    ranked = sorted(
        scored_figures,
        key=lambda s: (not getattr(s, "rejected", False), getattr(s, "total", 0.0)),
        reverse=True,
    )

    try:
        from PIL import Image
        import io
    except Exception as exc:
        logger.debug("PIL unavailable for debug ranked arXiv save: %s", exc)
        return

    for i, scored in enumerate(ranked, start=1):
        target = rank_dir / f"top_{i:02d}.png"
        try:
            img = Image.open(io.BytesIO(scored.figure.image_data)).convert("RGB")
            img.save(target, "PNG")
        except Exception as exc:
            logger.debug("Failed to save ranked arXiv figure #%d: %s", i, exc)


def _build_credit(candidate: ImageCandidate) -> str | None:
    if candidate.source == "unsplash" and candidate.context_text:
        return candidate.context_text
    if candidate.source in ("github", "huggingface", "web"):
        return candidate.url
    return None
