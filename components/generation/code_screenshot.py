from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)


def take_code_screenshot(code: str, output_path: Path) -> bool:
    """
    Generates a code screenshot using carbon.now.sh via Playwright.

    Falls back to Pygments + Playwright if carbon.now.sh fails.

    Returns:
        True if the screenshot was saved, False otherwise.
    """
    success = _screenshot_via_carbon(code, output_path)
    if not success:
        logger.info("Trying Pygments fallback for code screenshot.")
        success = _screenshot_via_pygments(code, output_path)
    return success


def _screenshot_via_carbon(code: str, output_path: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed.")
        return False

    encoded = urllib.parse.quote(code)
    url = (
        f"https://carbon.now.sh/?bg=rgba%28171%2C184%2C195%2C1%29"
        f"&t=dracula&wt=none&l=python&ds=true&dsyoff=20px"
        f"&dsblur=68px&wc=true&wa=true&pv=56px&ph=56px"
        f"&ln=false&fl=1&fm=Hack&fs=14px&lh=133%25"
        f"&si=false&es=2x&wm=false&code={encoded}"
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30_000)
            page.wait_for_selector("#export-container", timeout=15_000)
            container = page.query_selector("#export-container")
            if container is None:
                browser.close()
                return False
            container.screenshot(path=str(output_path))
            browser.close()
            logger.info("carbon.now.sh screenshot saved to %s", output_path)
            return True
    except Exception as exc:
        logger.warning("carbon.now.sh screenshot failed: %s", exc)
        return False


def _screenshot_via_pygments(code: str, output_path: Path) -> bool:
    try:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import PythonLexer
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Pygments or Playwright not installed.")
        return False

    formatter = HtmlFormatter(
        style="native",
        full=True,
        title="Code",
        prestyles="padding: 24px; border-radius: 8px;",
    )
    html_code = highlight(code, PythonLexer(), formatter)
    html_path = output_path.parent / "_code_preview.html"

    try:
        html_path.write_text(html_code, encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.goto(f"file://{html_path.resolve()}")
            page.screenshot(path=str(output_path), full_page=True)
            browser.close()
        html_path.unlink(missing_ok=True)
        logger.info("Pygments screenshot saved to %s", output_path)
        return True
    except Exception as exc:
        logger.warning("Pygments screenshot failed: %s", exc)
        if html_path.exists():
            html_path.unlink()
        return False
