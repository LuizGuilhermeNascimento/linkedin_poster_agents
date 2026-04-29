from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from app.config import settings, runtime_paths
from components.llm import client as llm
from components.search import arxiv_client, tavily_client
from domain.research import ResearchResult
from utils.text import extract_json_array

logger = logging.getLogger(__name__)

TAVILY_QUERIES = [
    "machine learning breakthroughs last week",
    "new AI tools released this week",
    "data science trending topics LinkedIn",
    "new ML framework library release",
    "artificial intelligence research news",
]

RESEARCHER_PROMPT_PATH = Path(__file__).parent.parent / "components" / "llm" / "prompts" / "researcher.txt"


def fetch_weekly_topics(n: int = 3) -> list[ResearchResult]:
    """
    Fetches and selects the n most relevant ML/DS topics of the week.

    Combines Tavily (web) and arXiv (papers), sends to LLM for ranking,
    returns top n as ResearchResult.
    """
    raw_results_path = runtime_paths.raw_results_file

    if raw_results_path:
        raw_results = _load_raw_results(raw_results_path)
        logger.info("Raw results loaded from %s", raw_results_path)
    else:
        raw_results = _collect_raw_results()
        saved_path = _save_raw_results(raw_results, runtime_paths.raw_results_dir)
        logger.info("Raw results saved to %s", saved_path)

    return _rank_with_llm(raw_results, n=n)


def _load_raw_results(raw_results_path: Path) -> list[dict]:
    raw_text = raw_results_path.read_text(encoding="utf-8")
    parsed = json.loads(raw_text)
    if not isinstance(parsed, list):
        raise ValueError("Raw results file must contain a JSON array")
    return parsed


def _save_raw_results(raw_results: list[dict], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = output_dir / f"raw_results_{stamp}.json"
    raw_path.write_text(
        json.dumps(raw_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return raw_path


def _collect_raw_results() -> list[dict]:
    results: list[dict] = []

    for query in TAVILY_QUERIES:
        try:
            hits = tavily_client.search(query, max_results=5)
            results.extend(hits)
            logger.info("Tavily '%s': %d results", query, len(hits))
        except Exception as exc:
            logger.warning("Tavily query failed '%s': %s", query, exc)

    try:
        papers = arxiv_client.search_recent_papers(
            categories=["cs.LG", "cs.AI", "stat.ML"],
            max_results=10,
        )
        results.extend(papers)
        logger.info("arXiv: %d papers retrieved", len(papers))
    except Exception as exc:
        logger.warning("arXiv search failed: %s", exc)

    return results


def _rank_with_llm(raw_results: list[dict], n: int) -> list[ResearchResult]:
    prompt_template = RESEARCHER_PROMPT_PATH.read_text(encoding="utf-8")
    raw_results_text = json.dumps(raw_results, ensure_ascii=False, indent=2)
    prompt = (
        prompt_template
        .replace("{n_posts}", str(n))
        .replace("{raw_results}", raw_results_text)
    )

    response_raw = llm.complete(prompt, max_tokens=32768)

    _write_debug_log(
        log_path=runtime_paths.researcher_log_file,
        agent_name="researcher",
        prompt=prompt,
        raw_output=response_raw,
    )

    raw_list = extract_json_array(response_raw)

    results: list[ResearchResult] = []
    for item in raw_list[:n]:
        results.append(ResearchResult(
            title=item.get("title", ""),
            summary=item.get("summary", ""),
            source_url=item.get("source_url", ""),
            source_type=item.get("source_type", "trend"),
            arxiv_id=item.get("arxiv_id") or None,
            suggested_angle=item.get("suggested_angle", ""),
            illustration_hint=item.get("illustration_hint", "none"),
            raw_sources=raw_results,
        ))

    return results


def _write_debug_log(
    log_path: Path | None,
    agent_name: str,
    prompt: str,
    raw_output: str,
) -> None:
    if not log_path:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    content = (
        f"[{timestamp}] agent={agent_name}\n"
        "--- INPUT PROMPT ---\n"
        f"{prompt}\n"
        "--- RAW OUTPUT ---\n"
        f"{raw_output}\n\n"
    )
    with log_path.open("a", encoding="utf-8") as f:
        f.write(content)
