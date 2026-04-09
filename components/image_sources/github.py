from __future__ import annotations

import base64
import logging
import re
from urllib.parse import urljoin

import requests

from app.config import settings
from domain.image import ImageCandidate
from .base import ImageSource

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
HEADERS = {"User-Agent": "linkedin-ml-pipeline/1.0 (educational project)"}

# Patterns for Markdown images: ![alt](url)
MD_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
# Patterns for HTML img tags: <img src="..." alt="..." width="...">
HTML_IMG_PATTERN = re.compile(
    r'<img\s[^>]*src=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?[^>]*(?:width=["\'](\d+)["\'])?',
    re.IGNORECASE,
)


class GitHubImageSource(ImageSource):
    """
    Fetches images from GitHub repository READMEs.

    Searches repos matching the query, extracts diagram/illustration images
    from README files, ignoring badges and small icons.
    """

    def __init__(self, token: str | None = None) -> None:
        self._token = token or settings.github_token
        self._headers = {**HEADERS}
        if self._token:
            self._headers["Authorization"] = f"Bearer {self._token}"

    def search(self, query: str, max_results: int = 5) -> list[ImageCandidate]:
        repos = self._search_repos(query, per_page=3)
        candidates: list[ImageCandidate] = []

        for repo in repos:
            readme_images = self._extract_readme_images(repo)
            for img in readme_images:
                img.query_origin = query
            candidates.extend(readme_images)
            if len(candidates) >= max_results:
                break

        return candidates[:max_results]

    def _search_repos(self, query: str, per_page: int = 3) -> list[dict]:
        try:
            response = requests.get(
                f"{GITHUB_API}/search/repositories",
                headers=self._headers,
                params={"q": query, "sort": "stars", "per_page": per_page},
                timeout=15,
            )
            response.raise_for_status()
            return response.json().get("items", [])
        except requests.RequestException as exc:
            logger.warning("GitHub repo search failed for '%s': %s", query, exc)
            return []

    def _extract_readme_images(self, repo: dict) -> list[ImageCandidate]:
        full_name = repo.get("full_name", "")
        default_branch = repo.get("default_branch", "main")

        readme_content = self._fetch_readme(full_name)
        if not readme_content:
            return []

        raw_base = f"https://raw.githubusercontent.com/{full_name}/{default_branch}/"
        html_base = f"https://github.com/{full_name}/raw/{default_branch}/"

        candidates: list[ImageCandidate] = []

        # Extract markdown images
        for match in MD_IMAGE_PATTERN.finditer(readme_content):
            alt_text = match.group(1)
            img_url = match.group(2)

            if _is_badge(img_url, alt_text):
                continue

            img_url = _resolve_github_url(img_url, raw_base, html_base)
            if not img_url:
                continue

            candidates.append(ImageCandidate(
                url=img_url,
                source="github",
                alt_text=alt_text,
                context_text=f"GitHub README: {full_name}",
            ))

        # Extract HTML img tags
        for match in HTML_IMG_PATTERN.finditer(readme_content):
            img_url = match.group(1)
            alt_text = match.group(2) or ""
            width_str = match.group(3) or "0"

            if _is_badge(img_url, alt_text):
                continue

            try:
                width = int(width_str)
                if width > 0 and width < 100:
                    continue
            except ValueError:
                pass

            img_url = _resolve_github_url(img_url, raw_base, html_base)
            if not img_url:
                continue

            candidates.append(ImageCandidate(
                url=img_url,
                source="github",
                alt_text=alt_text,
                context_text=f"GitHub README: {full_name}",
            ))

        return candidates

    def _fetch_readme(self, full_name: str) -> str | None:
        try:
            response = requests.get(
                f"{GITHUB_API}/repos/{full_name}/readme",
                headers=self._headers,
                timeout=15,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            content = data.get("content", "")
            encoding = data.get("encoding", "base64")
            if encoding == "base64":
                return base64.b64decode(content).decode("utf-8", errors="replace")
            return content
        except Exception as exc:
            logger.debug("Failed to fetch README for %s: %s", full_name, exc)
            return None


BADGE_URL_PATTERN = re.compile(
    r"(badge|shield|travis|codecov|license|version|build|status|npm|pypi|"
    r"img\.shields\.io|travis-ci|circleci|appveyor|gitlab\.com/.*badges)",
    re.IGNORECASE,
)
BADGE_ALT_PATTERN = re.compile(
    r"(build|ci|coverage|license|version|downloads|status|badge)",
    re.IGNORECASE,
)


def _is_badge(url: str, alt_text: str = "") -> bool:
    return bool(BADGE_URL_PATTERN.search(url)) or bool(BADGE_ALT_PATTERN.search(alt_text))


def _resolve_github_url(url: str, raw_base: str, html_base: str) -> str | None:
    if url.startswith("data:"):
        return None
    if url.startswith("http://") or url.startswith("https://"):
        # Convert github.com blob URLs to raw URLs
        if "github.com" in url and "/blob/" in url:
            url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        return url
    if url.startswith("//"):
        return f"https:{url}"
    # Relative URL — convert to raw.githubusercontent.com
    if url.startswith("/"):
        return None  # Absolute path within domain — skip
    return urljoin(raw_base, url)
