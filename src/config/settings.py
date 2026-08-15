"""
Central configuration. Nothing here is a secret or a hardcoded provider
limit -- everything is sourced from environment variables so behavior
can be tuned without code changes (per assessment §17 scale requirement).
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = Field(..., description="postgresql://user:pass@host:port/dbname")
    db_pool_min_size: int = 2
    db_pool_max_size: int = 10

    # --- arXiv ---
    arxiv_api_base: str = "http://export.arxiv.org/api/query"
    arxiv_request_delay_seconds: float = 3.5  # documented ceiling is 3 req/s; stay under it
    arxiv_page_size: int = 100
    arxiv_max_results: int = 2000
    arxiv_search_query: str = "cat:cs.AI"
    arxiv_http_timeout_seconds: float = 20.0

    # --- GitHub ---
    github_token: str | None = Field(default=None, description="required for 5000/hr authenticated tier")
    github_api_base: str = "https://api.github.com"
    github_max_concurrency: int = 5
    github_http_timeout_seconds: float = 15.0

    # --- Retry / backoff (generic, used across external calls) ---
    max_retry_attempts: int = 5
    retry_backoff_base_seconds: float = 1.0
    retry_backoff_max_seconds: float = 60.0
    retry_jitter_seconds: float = 0.5

    # --- Google Sheets ---
    google_service_account_json_path: str | None = None
    google_sheets_spreadsheet_id: str | None = None
    sheets_research_papers_tab: str = "Research Papers"
    sheets_batch_size: int = 500
    sheets_http_timeout_seconds: float = 30.0

    # --- Pipeline ---
    pipeline_batch_size: int = 50
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env/.env
