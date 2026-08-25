from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    return [item.strip() for item in value.split(",") if item.strip()]


class AIOrbitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    output_dir: str = Field(default="data", validation_alias="AI_ORBIT_OUTPUT_DIR")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    http_timeout_seconds: float = Field(default=20.0, validation_alias="AI_ORBIT_HTTP_TIMEOUT_SECONDS")
    max_retry_attempts: int = Field(default=3, validation_alias="AI_ORBIT_MAX_RETRY_ATTEMPTS")
    retry_backoff_base_seconds: float = Field(default=0.5, validation_alias="AI_ORBIT_RETRY_BACKOFF_BASE_SECONDS")
    retry_backoff_max_seconds: float = Field(default=8.0, validation_alias="AI_ORBIT_RETRY_BACKOFF_MAX_SECONDS")
    retry_jitter_seconds: float = Field(default=0.25, validation_alias="AI_ORBIT_RETRY_JITTER_SECONDS")
    ca_bundle: str = Field(default="/etc/ssl/certs/ca-certificates.crt", validation_alias="AI_ORBIT_CA_BUNDLE")

    github_api_base: str = Field(default="https://api.github.com", validation_alias="GITHUB_API_BASE")
    github_token: str | None = Field(default=None, validation_alias="GITHUB_TOKEN")
    github_search_query: str = Field(default="topic:artificial-intelligence stars:>1000", validation_alias="AI_ORBIT_GITHUB_SEARCH_QUERY")
    github_search_limit: int = Field(default=5, validation_alias="AI_ORBIT_GITHUB_SEARCH_LIMIT")
    github_company_orgs: list[str] = Field(default_factory=lambda: ["cohere-ai", "groq", "huggingface", "mistralai", "modelcontextprotocol"])

    pypi_packages: list[str] = Field(default_factory=lambda: ["openai", "anthropic", "groq", "mistralai"])

    npm_mcp_packages: list[str] = Field(default_factory=lambda: [
        "@modelcontextprotocol/server-filesystem",
        "@modelcontextprotocol/server-memory",
        "@modelcontextprotocol/server-sequential-thinking",
        "@modelcontextprotocol/server-github",
    ])

    huggingface_models_url: str = Field(default="https://huggingface.co/api/models", validation_alias="AI_ORBIT_HUGGINGFACE_MODELS_URL")
    openai_rss_url: str = Field(default="https://openai.com/news/rss.xml", validation_alias="AI_ORBIT_OPENAI_RSS_URL")

    @field_validator("github_company_orgs", "pypi_packages", "npm_mcp_packages", mode="before")
    @classmethod
    def parse_csv_lists(cls, value: str | list[str]) -> list[str]:
        return _split_csv(value)


def get_ai_orbit_settings() -> AIOrbitSettings:
    return AIOrbitSettings()
