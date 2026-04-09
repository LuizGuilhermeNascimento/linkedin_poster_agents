from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    tavily_api_key: str = "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"
    unsplash_access_key: str = ""
    github_token: str = ""
    posts_per_week: int = 5
    lmstudio_base_url: str = "http://localhost:1234/v1"
    lmstudio_model: str = "qwen/qwen3.5-9b"

    class Config:
        env_file = ".env"


settings = Settings()

OUTPUT_DIR = Path("output")


def get_current_week() -> str:
    """Returns ISO week label in YYYY-WW format."""
    today = datetime.now()
    year, week, _ = today.isocalendar()
    return f"{year}-{week:02d}"


@dataclass
class RuntimePaths:
    week_output_dir: Path = OUTPUT_DIR
    logs_dir: Path = OUTPUT_DIR / "logs"
    researcher_log_file: Path = OUTPUT_DIR / "logs" / "researcher_agent.log"
    writer_logs_dir: Path = OUTPUT_DIR / "logs"
    raw_results_file: Path | None = None
    raw_results_dir: Path = OUTPUT_DIR / "raw_results"


runtime_paths = RuntimePaths()


def set_runtime_inputs(
    raw_results_file: Path | None,
    raw_results_dir: Path | None,
) -> None:
    """Registers runtime inputs from the CLI."""
    runtime_paths.raw_results_file = raw_results_file
    runtime_paths.raw_results_dir = raw_results_dir or (OUTPUT_DIR / "raw_results")


def configure_runtime_paths(week_output_dir: Path) -> None:
    """Builds paths derived from the current run (week/logs)."""
    logs_dir = week_output_dir / "logs"
    runtime_paths.week_output_dir = week_output_dir
    runtime_paths.logs_dir = logs_dir
    runtime_paths.researcher_log_file = logs_dir / "researcher_agent.log"
    runtime_paths.writer_logs_dir = logs_dir
