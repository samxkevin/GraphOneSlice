from datetime import datetime, timezone

from src.ai_orbit.adapters.npm_search_tools import NpmSearchToolAdapter
from src.ai_orbit.config import AIOrbitSettings


def test_npm_search_candidate_filter_requires_explicit_ai_evidence_and_npm_url():
    adapter = NpmSearchToolAdapter(AIOrbitSettings(log_level="CRITICAL"))
    assert adapter._is_candidate_package(
        {
            "name": "ai-tool",
            "description": "SDK for LLM agents",
            "keywords": ["llm", "agents"],
            "links": {"npm": "https://www.npmjs.com/package/ai-tool"},
        }
    )
    assert not adapter._is_candidate_package(
        {
            "name": "ordinary-logger",
            "description": "Small logging helper",
            "keywords": ["logs"],
            "links": {"npm": "https://www.npmjs.com/package/ordinary-logger"},
        }
    )
    assert not adapter._is_candidate_package(
        {
            "name": "ai-without-url",
            "description": "AI package without a stable npm URL",
            "keywords": ["ai"],
            "links": {},
        }
    )
    assert not adapter._is_mcp_package("ai", "AI SDK with MCP support listed only as a keyword elsewhere")
    assert adapter._is_mcp_package("comfyui-mcp", "Local-first MCP server for ComfyUI")


def test_npm_search_record_marks_mcp_and_creative_from_observed_terms():
    adapter = NpmSearchToolAdapter(AIOrbitSettings(log_level="CRITICAL"))
    record = adapter._record_from_package(
        search_object={
            "package": {
                "name": "comfyui-mcp",
                "description": "MCP server for ComfyUI image generation",
                "keywords": ["mcp", "comfyui", "image"],
                "version": "1.0.0",
                "date": "2026-01-01T00:00:00.000Z",
                "links": {"npm": "https://www.npmjs.com/package/comfyui-mcp"},
            },
            "downloads": {"weekly": 10},
        },
        package_doc={
            "name": "comfyui-mcp",
            "description": "MCP server for ComfyUI image generation",
            "dist-tags": {"latest": "1.0.0"},
            "versions": {
                "1.0.0": {
                    "name": "comfyui-mcp",
                    "description": "MCP server for ComfyUI image generation",
                    "keywords": ["mcp", "comfyui", "image"],
                    "license": "MIT",
                    "bin": {"comfyui-mcp": "dist/index.js"},
                }
            },
        },
        source_url="https://registry.npmjs.org/comfyui-mcp",
        query="keywords:stable-diffusion",
        fetched_at=datetime.now(timezone.utc),
    )
    assert record is not None
    assert record.entity_type == "mcp"
    assert "MCP" in record.categories
    assert "Creative" in record.categories
    assert record.metadata["mcp"]["installation_method"] == "npm package comfyui-mcp"
