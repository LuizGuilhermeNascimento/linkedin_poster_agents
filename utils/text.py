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
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    start = text.find("[")
    if start == -1:
        raise ValueError(
            f"No JSON array found in LLM response.\nResponse: {text[:300]}"
        )

    array_text = _extract_first_json_array(text[start:])
    try:
        return json.loads(array_text)
    except json.JSONDecodeError as exc:
        repaired = _repair_common_json_quote_issues(array_text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError as repair_exc:
            raise ValueError(
                f"Invalid JSON in LLM response: {repair_exc}\n"
                f"Response (from '['): {array_text[:300]}"
            ) from repair_exc


def _extract_first_json_array(text: str) -> str:
    """Extracts the first complete JSON array from text using bracket matching."""
    depth = 0
    in_string = False
    escaped = False

    for i, ch in enumerate(text):
        if not in_string:
            if ch == '"':
                in_string = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[: i + 1]
        else:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False

    return text


def _repair_common_json_quote_issues(payload: str) -> str:
    """
    Repairs malformed JSON where inner double quotes inside strings are unescaped.

    Example fixed: "title": "A "quoted" title" -> "title": "A \"quoted\" title"
    """
    result: list[str] = []
    in_string = False
    escaped = False
    i = 0

    while i < len(payload):
        ch = payload[i]

        if not in_string:
            result.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if escaped:
            result.append(ch)
            escaped = False
            i += 1
            continue

        if ch == "\\":
            result.append(ch)
            escaped = True
            i += 1
            continue

        if ch == '"':
            j = i + 1
            while j < len(payload) and payload[j] in {" ", "\t", "\n", "\r"}:
                j += 1

            # Valid JSON string terminators for keys/values.
            if j >= len(payload) or payload[j] in {",", "]", "}", ":"}:
                result.append(ch)
                in_string = False
            else:
                # Inner quote inside a string literal: escape it.
                result.append('\\"')
            i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


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
