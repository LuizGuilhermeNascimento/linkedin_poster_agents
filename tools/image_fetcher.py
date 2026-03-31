import logging
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from config import settings

if TYPE_CHECKING:
    from agents.researcher import ResearchResult

logger = logging.getLogger(__name__)


class ImageFetcher:
    def __init__(self) -> None:
        self.images_dir = Path(settings.output_images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def fetch_paper_figure(self, arxiv_id: str) -> tuple[str, str, str] | None:
        """Baixa PDF do arXiv e extrai a primeira figura relevante."""
        try:
            import fitz  # PyMuPDF

            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
            response = requests.get(pdf_url, timeout=60)
            response.raise_for_status()

            doc = fitz.open(stream=response.content, filetype="pdf")
            for page_num in range(min(5, len(doc))):
                page = doc[page_num]
                image_list = page.get_images(full=True)
                if not image_list:
                    continue
                xref = image_list[0][0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]

                if len(image_bytes) < 10_000:  # ignora ícones pequenos
                    continue

                ext = base_image["ext"]
                dest = self.images_dir / f"arxiv_{arxiv_id}_fig.{ext}"
                dest.write_bytes(image_bytes)
                return str(dest), pdf_url, f"arXiv:{arxiv_id}"

        except Exception:
            logger.warning("Falha ao extrair figura do arXiv %s", arxiv_id, exc_info=True)

        return None

    def fetch_repo_image(self, tool_name: str, source_url: str) -> tuple[str, str, str] | None:
        """Busca og:image ou primeira imagem do README via BeautifulSoup."""
        try:
            from bs4 import BeautifulSoup

            headers = {"User-Agent": "LinkedInPosterBot/1.0"}
            response = requests.get(source_url, headers=headers, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            og_image = soup.find("meta", property="og:image")
            if og_image:
                img_url = og_image.get("content", "")
                if img_url:
                    return self._download_image(img_url, "repo", source_url)

            readme_img = soup.find("img", src=True)
            if readme_img:
                img_url = readme_img["src"]
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(source_url)
                    img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
                return self._download_image(img_url, "repo", source_url)

        except Exception:
            logger.warning("Falha ao buscar imagem do repositório %s", source_url, exc_info=True)

        return None

    def fetch_code_screenshot(self, research: "ResearchResult") -> tuple[str, str, str] | None:
        """Gera screenshot de um snippet de código via Playwright + carbon.now.sh."""
        from tools.code_screenshot import CodeScreenshot

        screenshotter = CodeScreenshot()
        return screenshotter.generate(research)

    def fetch_stock_photo(self, topic: str) -> tuple[str, str, str] | None:
        """Busca imagem no Unsplash sobre o tema do post."""
        if not settings.unsplash_access_key:
            logger.warning("UNSPLASH_ACCESS_KEY não configurada. Pulando stock photo.")
            return None

        try:
            search_query = self._topic_to_english(topic)
            response = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": search_query, "per_page": 1, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {settings.unsplash_access_key}"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not results:
                return None

            photo = results[0]
            img_url = photo["urls"]["regular"]
            credit = f"Unsplash / @{photo['user']['username']}"
            return self._download_image(img_url, "unsplash", img_url, credit=credit)

        except Exception:
            logger.warning("Falha ao buscar stock photo para '%s'", topic, exc_info=True)

        return None

    def _download_image(
        self,
        url: str,
        prefix: str,
        source_url: str,
        credit: str | None = None,
    ) -> tuple[str, str, str] | None:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "image/jpeg")
            ext = content_type.split("/")[-1].split(";")[0].strip() or "jpg"
            if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
                ext = "jpg"

            import hashlib
            name = hashlib.md5(url.encode()).hexdigest()[:12]
            dest = self.images_dir / f"{prefix}_{name}.{ext}"
            dest.write_bytes(response.content)
            return str(dest), source_url, credit or source_url

        except Exception:
            logger.warning("Falha ao baixar imagem: %s", url, exc_info=True)
            return None

    @staticmethod
    def _topic_to_english(topic: str) -> str:
        """Extrai palavras-chave em inglês do tópico para busca no Unsplash."""
        keywords = ["machine learning", "neural network", "data science", "artificial intelligence",
                    "deep learning", "data pipeline", "algorithm", "model training"]
        topic_lower = topic.lower()
        for kw in keywords:
            if any(word in topic_lower for word in kw.split()):
                return kw
        return topic[:50]
