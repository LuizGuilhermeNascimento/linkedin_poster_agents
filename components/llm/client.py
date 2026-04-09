from __future__ import annotations

from openai import OpenAI

from app.config import settings


def create_client() -> OpenAI:
    """Returns a configured OpenAI-compatible LLM client."""
    return OpenAI(base_url=settings.lmstudio_base_url, api_key="lm-studio")


def complete(prompt: str, max_tokens: int = 8192) -> str:
    """
    Sends a prompt to the LLM and returns the response text.

    Strips leading/trailing whitespace from the response.
    """
    client = create_client()
    message = client.chat.completions.create(
        model=settings.lmstudio_model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return (message.choices[0].message.content or "").strip()
