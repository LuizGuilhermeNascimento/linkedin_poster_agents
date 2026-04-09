from __future__ import annotations

import json


def strip_think_block(text: str) -> str:
    """Removes the <think>...</think> block produced by reasoning models."""
    start = text.find("<think>")
    end = text.find("</think>")
    if start != -1 and end != -1:
        return text[end + len("</think>"):].strip()
    return text


def extract_json_array(text: str) -> list[dict]:
    """
    Extracts the first JSON array found in text.

    Handles reasoning preamble and markdown code fences.
    """
    text = strip_think_block(text)
    start = text.find("[")
    if start == -1:
        raise ValueError(
            f"No JSON array found in LLM response.\nResponse: {text[:300]}"
        )
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in LLM response: {exc}\n"
            f"Response (from '['): {text[start:start + 300]}"
        ) from exc


def extract_json_object(text: str) -> dict:
    """
    Extracts the first JSON object found in text.

    Handles reasoning preamble and markdown code fences.
    """
    text = strip_think_block(text)
    # Strip markdown fences if present
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    start = text.find("{")
    if start == -1:
        raise ValueError(
            f"No JSON object found in LLM response.\nResponse: {text[:300]}"
        )
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in LLM response: {exc}\n"
            f"Response (from '{{'): {text[start:start + 300]}"
        ) from exc


def extract_post_content(raw: str) -> str:
    """Extracts content between <post>...</post> tags, stripping think blocks."""
    text = strip_think_block(raw)
    start = text.rfind("<post>")
    end = text.rfind("</post>")
    if start != -1 and end != -1 and end > start:
        return text[start + len("<post>"):end].strip()
    if start != -1:
        return text[start + len("<post>"):].strip()
    return text


def extract_code_content(raw: str) -> str:
    """Strips markdown code fences from a code response."""
    if "```" in raw:
        lines = raw.splitlines()
        return "\n".join(line for line in lines if not line.startswith("```")).strip()
    return raw
