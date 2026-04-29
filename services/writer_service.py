from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import runtime_paths
from components.llm import client as llm
from components.generation.code_screenshot import take_code_screenshot
from domain.post import PostDraft
from domain.research import ResearchResult
from services.image_service import get_best_image
from utils.text import extract_post_content, extract_code_content

logger = logging.getLogger(__name__)

WRITER_PROMPT_PATH = Path(__file__).parent.parent / "components" / "llm" / "prompts" / "writer.txt"

# Module-level log file path, set per post generation
_debug_log_file: Path | None = None


def create_post(
    result: ResearchResult,
    output_dir: Path,
    week: str,
    debug: bool = False,
) -> PostDraft:
    """
    Generates the text and illustration for a post and saves files to output_dir.

    Returns:
        PostDraft with complete metadata.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    _set_debug_log(output_dir)

    text = _generate_text(result)
    image_path, image_url, image_credit, image_result = _fetch_image(result, output_dir, text, debug=debug)

    draft = PostDraft(
        id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
        week=week,
        research=result,
        text=text,
        image_path=str(image_path) if image_path else None,
        image_url=image_url,
        image_credit=image_credit,
    )

    _save_files(draft, output_dir, image_result)
    return draft


def _set_debug_log(output_dir: Path) -> None:
    global _debug_log_file
    _debug_log_file = runtime_paths.writer_logs_dir / f"writer_agent_{output_dir.name}.log"


def _generate_text(result: ResearchResult) -> str:
    prompt_template = WRITER_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{title}", result.title)
        .replace("{summary}", result.summary)
        .replace("{suggested_angle}", result.suggested_angle)
        .replace("{source_url}", result.source_url)
    )

    response_raw = llm.complete(prompt, max_tokens=32768)
    _write_debug_log(agent_name="writer", prompt=prompt, raw_output=response_raw)
    return extract_post_content(response_raw)


def _fetch_image(
    result: ResearchResult,
    output_dir: Path,
    post_text: str,
    debug: bool = False,
) -> tuple[Path | None, str | None, str | None, object]:
    """
    Fetches the image using the image pipeline, with code screenshot as a special case.

    Returns:
        (image_path, image_url, image_credit, image_result)
    """
    if result.illustration_hint == "code":
        code_snippet = _generate_code_snippet(result, post_text)
        image_path = output_dir / "image.png"
        success = take_code_screenshot(code_snippet, image_path)
        if success:
            return image_path, None, "Generated via carbon.now.sh", None
        logger.info("Code screenshot failed — falling back to image pipeline")

    image_result = get_best_image(result, output_dir, debug=debug)

    if image_result.image_path:
        return image_result.image_path, image_result.image_url, image_result.credit, image_result

    return None, None, None, image_result


def _generate_code_snippet(result: ResearchResult, post_text: str) -> str:
    prompt = (
        f"Generate a self-contained, didactic Python snippet (max 20 lines) "
        f"that illustrates the concept of the following ML/DS topic.\n\n"
        f"Topic: {result.title}\n"
        f"Summary: {result.summary}\n\n"
        f"Return ONLY the Python code, no explanations or markdown."
    )
    response_raw = llm.complete(prompt, max_tokens=512)
    _write_debug_log(agent_name="writer_code", prompt=prompt, raw_output=response_raw)
    return extract_code_content(response_raw)


def _write_debug_log(agent_name: str, prompt: str, raw_output: str) -> None:
    log_path = _debug_log_file
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


def _save_files(draft: PostDraft, output_dir: Path, image_result=None) -> None:
    (output_dir / "post.txt").write_text(draft.text, encoding="utf-8")
    meta = draft.model_dump()
    (output_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if image_result and image_result.candidates:
        _save_image_candidates(image_result.candidates, output_dir)


def _save_image_candidates(candidates, output_dir: Path) -> None:
    from dataclasses import asdict
    ranked = []
    for sc in candidates:
        ranked.append({
            "score": round(sc.score, 4),
            "url": sc.candidate.url,
            "source": sc.candidate.source,
            "alt_text": sc.candidate.alt_text,
            "width": sc.candidate.width,
            "height": sc.candidate.height,
            "query_origin": sc.candidate.query_origin,
            "context_text": sc.candidate.context_text[:120] if sc.candidate.context_text else "",
        })
    (output_dir / "image_candidates.json").write_text(
        json.dumps(ranked, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
