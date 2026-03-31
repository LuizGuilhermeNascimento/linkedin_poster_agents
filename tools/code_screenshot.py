import logging
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

import anthropic

from config import settings

if TYPE_CHECKING:
    from agents.researcher import ResearchResult

logger = logging.getLogger(__name__)


class CodeScreenshot:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.images_dir = Path(settings.output_images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, research: "ResearchResult") -> tuple[str, str, str] | None:
        """Gera um snippet de código e captura screenshot via carbon.now.sh."""
        snippet = self._generate_snippet(research)
        if not snippet:
            return None

        return self._screenshot_carbon(snippet, research.title)

    def _generate_snippet(self, research: "ResearchResult") -> str | None:
        prompt = (
            f"Gere um snippet Python relevante, autocontido e com no máximo 20 linhas "
            f"sobre: {research.title}\n\n"
            f"Resumo: {research.summary}\n\n"
            f"Retorne APENAS o código Python, sem explicações, sem markdown, sem ```."
        )

        response = self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )

        return next(
            (block.text.strip() for block in response.content if block.type == "text"),
            None,
        )

    def _screenshot_carbon(self, code: str, title: str) -> tuple[str, str, str] | None:
        """Captura screenshot do carbon.now.sh via Playwright."""
        try:
            from playwright.sync_api import sync_playwright

            encoded_code = quote(code)
            url = (
                f"https://carbon.now.sh/?l=python"
                f"&bg=rgba(171%2C184%2C195%2C1)"
                f"&t=monokai"
                f"&code={encoded_code}"
            )

            import hashlib
            name = hashlib.md5(code.encode()).hexdigest()[:12]
            dest = self.images_dir / f"code_{name}.png"

            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": 1280, "height": 720})
                page.goto(url, wait_until="networkidle", timeout=30_000)
                page.wait_for_selector("[data-testid='export-menu-button']", timeout=10_000)

                # Captura apenas o editor de código
                editor = page.query_selector(".CodeMirror-scroll")
                if editor:
                    editor.screenshot(path=str(dest))
                else:
                    page.screenshot(path=str(dest))

                browser.close()

            return str(dest), url, "carbon.now.sh"

        except Exception:
            logger.warning("Falha ao gerar screenshot do carbon.now.sh", exc_info=True)
            return None
