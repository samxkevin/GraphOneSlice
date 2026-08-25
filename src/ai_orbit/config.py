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

    official_sdk_model_limit_per_provider: int = Field(default=8, validation_alias="AI_ORBIT_OFFICIAL_SDK_MODEL_LIMIT_PER_PROVIDER")

    npm_mcp_packages: list[str] = Field(default_factory=lambda: [
        "@modelcontextprotocol/server-filesystem",
        "@modelcontextprotocol/server-memory",
        "@modelcontextprotocol/server-sequential-thinking",
        "@modelcontextprotocol/server-github",
    ])

    npm_search_tool_queries: list[str] = Field(default_factory=lambda: [
        "keywords:openai",
        "keywords:llm",
        "keywords:ai-sdk",
        "keywords:stable-diffusion",
        "keywords:model-context-protocol",
    ])
    npm_search_tool_limit_per_query: int = Field(default=6, validation_alias="AI_ORBIT_NPM_SEARCH_TOOL_LIMIT_PER_QUERY")
    npm_search_tool_max_records: int = Field(default=24, validation_alias="AI_ORBIT_NPM_SEARCH_TOOL_MAX_RECORDS")

    huggingface_models_url: str = Field(default="https://huggingface.co/api/models", validation_alias="AI_ORBIT_HUGGINGFACE_MODELS_URL")
    openai_rss_url: str = Field(default="https://openai.com/news/rss.xml", validation_alias="AI_ORBIT_OPENAI_RSS_URL")

    ai_tools_product_directory_api_url: str = Field(
        default="https://api.github.com/repos/lakey009/AI-Tools-List/contents/AIToolsList-Sample.json",
        validation_alias="AI_ORBIT_AI_TOOLS_PRODUCT_DIRECTORY_API_URL",
    )
    ai_tools_product_limit: int = Field(default=50, validation_alias="AI_ORBIT_AI_TOOLS_PRODUCT_LIMIT")

    models_dev_github_catalog_api_url: str = Field(
        default="https://api.github.com/repos/anomalyco/models.dev/contents/models.json?ref=dev",
        validation_alias="AI_ORBIT_MODELS_DEV_GITHUB_CATALOG_API_URL",
    )
    models_dev_model_limit: int = Field(default=12, validation_alias="AI_ORBIT_MODELS_DEV_MODEL_LIMIT")

    @field_validator("github_company_orgs", "pypi_packages", "npm_mcp_packages", "npm_search_tool_queries", mode="before")
    @classmethod
    def parse_csv_lists(cls, value: str | list[str]) -> list[str]:
        return _split_csv(value)


def get_ai_orbit_settings() -> AIOrbitSettings:
    return AIOrbitSettings()
