from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from ..core import config
from ..models.schemas import PostDraft, ResearchResult
from ..utils import image_fetcher
from ..utils.code_screenshot import take_code_screenshot

logger = logging.getLogger(__name__)

WRITER_PROMPT_PATH = Path(__file__).parent.parent / "config" / "writer_prompt.txt"
WRITER_DEBUG_LOG_FILE: Path | None = None


def create_post(
    result: ResearchResult,
    output_dir: Path,
    week: str,
) -> PostDraft:
    """
    Gera o texto e a ilustração do post e salva os arquivos em output_dir.

    Returns:
        PostDraft com metadados completos.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    _set_writer_debug_log_file(output_dir)

    text = _generate_text(result)
    image_path, image_url, image_credit = _fetch_image(result, output_dir, text)

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

    _save_files(draft, output_dir)
    return draft


def _set_writer_debug_log_file(output_dir: Path) -> None:
    global WRITER_DEBUG_LOG_FILE
    WRITER_DEBUG_LOG_FILE = (
        config.runtime_paths.writer_logs_dir / f"writer_agent_{output_dir.name}.log"
    )


def _generate_text(result: ResearchResult) -> str:
    prompt_template = WRITER_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template
        .replace("{title}", result.title)
        .replace("{summary}", result.summary)
        .replace("{suggested_angle}", result.suggested_angle)
        .replace("{source_url}", result.source_url)
    )

    client = OpenAI(base_url=config.settings.lmstudio_base_url, api_key="lm-studio")
    message = client.chat.completions.create(
        model=config.settings.lmstudio_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    response_raw = (message.choices[0].message.content or "").strip()
    _write_agent_debug_log(
        agent_name="writer",
        prompt=prompt,
        raw_output=response_raw,
    )
    return response_raw


def _fetch_image(
    result: ResearchResult,
    output_dir: Path,
    post_text: str,
) -> tuple[Path | None, str | None, str | None]:
    """
    Tenta obter a imagem de acordo com illustration_hint, com fallback em cascata.

    Returns:
        (image_path, image_url, image_credit)
    """
    hint = result.illustration_hint
    image_path = output_dir / "image.png"

    if hint == "paper_figure":
        if result.arxiv_id:
            success = image_fetcher.fetch_paper_figure(result.arxiv_id, image_path)
            if success:
                return image_path, f"https://arxiv.org/pdf/{result.arxiv_id}", f"arXiv:{result.arxiv_id}"
        logger.info("Fallback paper_figure → repo_image")
        hint = "repo_image"

    if hint == "repo_image":
        success, img_url = image_fetcher.fetch_repo_image(result.title, image_path)
        if success:
            return image_path, img_url, img_url
        logger.info("Fallback repo_image → stock_photo")
        hint = "stock_photo"

    if hint == "stock_photo":
        success, img_url, credit = image_fetcher.fetch_stock_photo(
            result.title, image_path
        )
        if success:
            return image_path, img_url, credit
        logger.info("stock_photo indisponível — sem imagem")
        return None, None, None

    if hint == "code":
        code_snippet = _generate_code_snippet(result, post_text)
        success = take_code_screenshot(code_snippet, image_path)
        if success:
            return image_path, None, "Gerado via carbon.now.sh"
        logger.info("Falha no screenshot de código — sem imagem")
        return None, None, None

    # hint == "none"
    return None, None, None


def _generate_code_snippet(
    result: ResearchResult,
    post_text: str,
) -> str:
    prompt = (
        f"Gere um snippet Python autocontido e didático (máximo 20 linhas) "
        f"que ilustre o conceito do seguinte tópico de ML/DS.\n\n"
        f"Tópico: {result.title}\n"
        f"Resumo: {result.summary}\n\n"
        f"Retorne APENAS o código Python, sem explicações ou markdown."
    )
    client = OpenAI(base_url=config.settings.lmstudio_base_url, api_key="lm-studio")
    message = client.chat.completions.create(
        model=config.settings.lmstudio_model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    code = (message.choices[0].message.content or "").strip()
    _write_agent_debug_log(
        agent_name="writer_code",
        prompt=prompt,
        raw_output=code,
    )
    # Remove possíveis fences
    if code.startswith("```"):
        lines = code.splitlines()
        code = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()
    return code


def _write_agent_debug_log(
    agent_name: str,
    prompt: str,
    raw_output: str,
) -> None:
    log_path = WRITER_DEBUG_LOG_FILE
    if not log_path:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    content = (
        f"[{timestamp}] agent={agent_name}\n"
        "--- INPUT PROMPT ---\n"
        f"{prompt}\n"
        "--- RAW OUTPUT ---\n"
        f"{raw_output}\n"
        "\n"
    )
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(content)


def _save_files(draft: PostDraft, output_dir: Path) -> None:
    (output_dir / "post.txt").write_text(draft.text, encoding="utf-8")

    meta = draft.model_dump()
    (output_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
