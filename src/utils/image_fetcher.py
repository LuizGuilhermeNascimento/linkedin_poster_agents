from __future__ import annotations

import io
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image

from ..core.config import settings

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "linkedin-ml-pipeline/1.0 (educational project)"}


def fetch_paper_figure(arxiv_id: str, output_path: Path) -> bool:
    """
    Baixa o PDF do arXiv e extrai a primeira figura relevante.

    Returns:
        True se uma imagem foi salva, False caso contrário.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF não instalado — pulando extração de figura.")
        return False

    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    try:
        response = requests.get(pdf_url, headers=HEADERS, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Falha ao baixar PDF arXiv %s: %s", arxiv_id, exc)
        return False

    try:
        doc = fitz.open(stream=response.content, filetype="pdf")
        for page in doc:
            images = page.get_images(full=True)
            for img_ref in images:
                xref = img_ref[0]
                base_image = doc.extract_image(xref)
                width = base_image.get("width", 0)
                height = base_image.get("height", 0)
                # Ignora ícones e imagens muito pequenas
                if width < 200 or height < 200:
                    continue
                image_bytes = base_image["image"]
                img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                img.save(output_path, "PNG")
                logger.info("Figura extraída do arXiv %s → %s", arxiv_id, output_path)
                return True
    except Exception as exc:
        logger.warning("Erro ao processar PDF arXiv %s: %s", arxiv_id, exc)

    return False


def fetch_repo_image(tool_name: str, output_path: Path) -> tuple[bool, str | None]:
    """
    Busca og:image de página GitHub ou HuggingFace para a ferramenta.

    Returns:
        (success, image_url) onde image_url é a origem da imagem.
    """
    from ..utils import tavily_search  # import local para evitar ciclo

    query = f"{tool_name} site:github.com OR site:huggingface.co"
    results = tavily_search.search(query, max_results=3)

    for result in results:
        url = result.get("url", "")
        if not ("github.com" in url or "huggingface.co" in url):
            continue
        image_url = _extract_og_image(url)
        if image_url and _download_image(image_url, output_path):
            return True, image_url

    return False, None


def fetch_stock_photo(query: str, output_path: Path) -> tuple[bool, str | None, str | None]:
    """
    Baixa uma imagem do Unsplash relacionada ao query.

    Returns:
        (success, image_url, credit) onde credit é a atribuição.
    """
    if not settings.unsplash_access_key:
        logger.warning("UNSPLASH_ACCESS_KEY não configurado — pulando stock photo.")
        return False, None, None

    params = {
        "query": query,
        "per_page": 1,
        "orientation": "landscape",
        "client_id": settings.unsplash_access_key,
    }
    try:
        response = requests.get(
            "https://api.unsplash.com/search/photos",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if not results:
            return False, None, None

        photo = results[0]
        image_url = photo["urls"]["regular"]
        username = photo["user"]["username"]
        credit = f"Unsplash / @{username}"

        if _download_image(image_url, output_path):
            return True, image_url, credit

    except requests.RequestException as exc:
        logger.warning("Falha ao buscar Unsplash: %s", exc)

    return False, None, None


def _extract_og_image(url: str) -> str | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        og_tag = soup.find("meta", property="og:image")
        if og_tag and og_tag.get("content"):
            return og_tag["content"]
    except requests.RequestException as exc:
        logger.debug("Falha ao acessar %s: %s", url, exc)
    return None


def _download_image(image_url: str, output_path: Path, max_retries: int = 3) -> bool:
    import time

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(image_url, headers=HEADERS, timeout=30)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                logger.warning(
                    "429 Too Many Requests para %s — aguardando %ds (tentativa %d/%d)",
                    image_url, retry_after, attempt, max_retries,
                )
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            img = Image.open(io.BytesIO(response.content)).convert("RGB")
            img.save(output_path, "PNG")
            return True
        except requests.HTTPError:
            raise
        except Exception as exc:
            logger.warning("Falha ao baixar imagem %s: %s", image_url, exc)
            return False

    logger.warning("Falha ao baixar imagem %s após %d tentativas (429)", image_url, max_retries)
    return False
