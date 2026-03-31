import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str

    # Tavily
    tavily_api_key: str = ""

    # LinkedIn
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    linkedin_access_token: str = ""
    linkedin_person_urn: str = ""

    # Unsplash
    unsplash_access_key: str = ""

    # Pipeline
    posts_per_week: int = 3
    schedule_days: str = "monday,wednesday,friday"
    schedule_time: str = "09:00"

    # Modelos e limites
    anthropic_model: str = "claude-opus-4-6"
    arxiv_max_results: int = 10
    tavily_max_results: int = 5

    # Diretórios
    output_queue_dir: str = "output/queue"
    output_published_dir: str = "output/published"
    output_images_dir: str = "output/queue/images"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
