import logging

import requests

from config import settings

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"


class LinkedInAPIError(Exception):
    """Levantada quando a LinkedIn API retorna um erro."""


class LinkedInAPI:
    def __init__(self) -> None:
        self.access_token = settings.linkedin_access_token
        self.person_urn = settings.linkedin_person_urn

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def upload_image(self, image_path: str) -> str:
        """
        Faz upload de imagem via LinkedIn Asset API e retorna o asset URN.

        Returns:
            str: URN do asset, ex: "urn:li:digitalmediaAsset:XXXXXXXX"
        """
        # 1. Registrar upload
        register_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": self.person_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }

        response = requests.post(
            f"{LINKEDIN_API_BASE}/assets?action=registerUpload",
            headers=self._headers,
            json=register_payload,
            timeout=30,
        )
        self._raise_for_status(response, "registerUpload")

        data = response.json()
        upload_url = data["value"]["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset_urn = data["value"]["asset"]

        # 2. Fazer upload do arquivo
        with open(image_path, "rb") as f:
            image_data = f.read()

        upload_response = requests.put(
            upload_url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            data=image_data,
            timeout=60,
        )
        self._raise_for_status(upload_response, "imageUpload")

        logger.info("Imagem enviada ao LinkedIn. Asset URN: %s", asset_urn)
        return asset_urn

    def create_post(self, text: str, image_asset_urn: str | None = None) -> str:
        """
        Publica um post no LinkedIn.

        Returns:
            str: URN do post criado.
        """
        content: dict = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "NONE" if not image_asset_urn else "IMAGE",
        }

        if image_asset_urn:
            content["media"] = [
                {
                    "status": "READY",
                    "media": image_asset_urn,
                }
            ]

        payload = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": content,
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
            },
        }

        response = requests.post(
            f"{LINKEDIN_API_BASE}/ugcPosts",
            headers=self._headers,
            json=payload,
            timeout=30,
        )
        self._raise_for_status(response, "ugcPosts")

        post_urn = response.headers.get("X-RestLi-Id", "")
        logger.info("Post publicado no LinkedIn. URN: %s", post_urn)
        return post_urn

    @staticmethod
    def _raise_for_status(response: requests.Response, context: str) -> None:
        if not response.ok:
            raise LinkedInAPIError(
                f"LinkedIn API error em {context}: "
                f"HTTP {response.status_code} — {response.text[:500]}"
            )
