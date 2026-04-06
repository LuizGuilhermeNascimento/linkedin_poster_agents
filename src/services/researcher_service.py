from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from ..core import config
from ..models.schemas import ResearchResult
from ..utils import arxiv_search, tavily_search

logger = logging.getLogger(__name__)

TAVILY_QUERIES = [
    "machine learning breakthroughs last week",
    "new AI tools released this week",
    "data science trending topics LinkedIn",
    "new ML framework library release",
    "artificial intelligence research news",
]

RESEARCHER_PROMPT_PATH = Path(__file__).parent.parent / "config" / "researcher_prompt.txt"


def fetch_weekly_topics(n: int = 3) -> list[ResearchResult]:
    """
    Busca e seleciona os n tópicos mais relevantes da semana em ML/DS.

    Combina resultados do Tavily (web geral) e arXiv (papers científicos),
    envia para o LLM classificar e ranquear, retorna top n como ResearchResult.
    """
    raw_results_path = config.runtime_paths.raw_results_file

    if raw_results_path:
        raw_results = _load_raw_results(raw_results_path)
        logger.info("Raw results carregados de %s", raw_results_path)
    else:
        raw_results = _collect_raw_results()
        saved_path = _save_raw_results(raw_results, config.runtime_paths.raw_results_dir)
        logger.info("Raw results salvos em %s", saved_path)

    ranked = _rank_with_llm(raw_results, n=n)
    return ranked


def _load_raw_results(raw_results_path: Path) -> list[dict]:
    raw_text = raw_results_path.read_text(encoding="utf-8")
    parsed = json.loads(raw_text)
    if not isinstance(parsed, list):
        raise ValueError("Arquivo de raw results deve conter um array JSON")
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
            hits = tavily_search.search(query, max_results=5)
            results.extend(hits)
            logger.info("Tavily '%s': %d resultados", query, len(hits))
        except Exception as exc:
            logger.warning("Falha Tavily query '%s': %s", query, exc)

    try:
        papers = arxiv_search.search_recent_papers(
            categories=["cs.LG", "cs.AI", "stat.ML"],
            max_results=10,
        )
        results.extend(papers)
        logger.info("arXiv: %d papers recuperados", len(papers))
    except Exception as exc:
        logger.warning("Falha arXiv: %s", exc)

    return results


def _strip_think_block(text: str) -> str:
    """Remove o bloco <think>...</think> produzido por modelos com reasoning."""
    start = text.find("<think>")
    end = text.find("</think>")
    if start != -1 and end != -1:
        return text[end + len("</think>"):].strip()
    return text


def _extract_json_array(text: str) -> list[dict]:
    """
    Extrai o primeiro array JSON encontrado no texto.

    Lida com modelos que produzem raciocínio antes do JSON ou que envolvem
    a resposta em markdown code fences.
    """
    text = _strip_think_block(text)
    start = text.find("[")
    if start == -1:
        raise ValueError(f"Nenhum array JSON encontrado na resposta do LLM.\nResposta: {text[:300]}")
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido na resposta do LLM: {exc}\nResposta (a partir do '['): {text[start:start+300]}") from exc


def _rank_with_llm(
    raw_results: list[dict],
    n: int,
) -> list[ResearchResult]:
    prompt_template = RESEARCHER_PROMPT_PATH.read_text(encoding="utf-8")
    raw_results_text = json.dumps(raw_results, ensure_ascii=False, indent=2)
    prompt = prompt_template.replace("{raw_results}", raw_results_text)

    client = OpenAI(base_url=config.settings.lmstudio_base_url, api_key="lm-studio")
    message = client.chat.completions.create(
        model=config.settings.lmstudio_model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    response_raw = (message.choices[0].message.content or "").strip()
    _write_agent_debug_log(
        config.runtime_paths.researcher_log_file,
        agent_name="researcher",
        prompt=prompt,
        raw_output=response_raw,
    )

    raw_list: list[dict] = _extract_json_array(response_raw)

    results: list[ResearchResult] = []
    for item in raw_list[:n]:
        results.append(
            ResearchResult(
                title=item.get("title", ""),
                summary=item.get("summary", ""),
                source_url=item.get("source_url", ""),
                source_type=item.get("source_type", "trend"),
                arxiv_id=item.get("arxiv_id") or None,
                suggested_angle=item.get("suggested_angle", ""),
                illustration_hint=item.get("illustration_hint", "none"),
                raw_sources=raw_results,
            )
        )

    return results


def _write_agent_debug_log(
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
        f"{raw_output}\n"
        "\n"
    )
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(content)
