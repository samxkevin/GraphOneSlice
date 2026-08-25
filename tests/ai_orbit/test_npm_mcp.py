from datetime import datetime, timezone

from src.ai_orbit.adapters.npm_mcp import NpmMcpAdapter
from src.ai_orbit.config import AIOrbitSettings


def test_npm_mcp_new_category_uses_published_timestamp_not_version_shape():
    adapter = NpmMcpAdapter(AIOrbitSettings(log_level="CRITICAL"))
    record = adapter._package_record(
        "@modelcontextprotocol/server-example",
        {
            "name": "@modelcontextprotocol/server-example",
            "description": "MCP server for filesystem access",
            "dist-tags": {"latest": "2026.7.10"},
            "time": {"2026.7.10": "2024-12-31T23:59:59.000Z"},
            "versions": {
                "2026.7.10": {
                    "name": "@modelcontextprotocol/server-example",
                    "description": "MCP server for filesystem access",
                }
            },
        },
        "https://registry.npmjs.org/@modelcontextprotocol%2Fserver-example",
        fetched_at=datetime.now(timezone.utc),
    )
    assert record is not None
    assert "New/Recently Added" not in record.categories
    assert record.metadata["mcp"]["latest_version_published_at"] == "2024-12-31T23:59:59.000Z"


def test_npm_mcp_recent_published_timestamp_is_source_backed_category_evidence():
    adapter = NpmMcpAdapter(AIOrbitSettings(log_level="CRITICAL"))
    record = adapter._package_record(
        "@modelcontextprotocol/server-example",
        {
            "name": "@modelcontextprotocol/server-example",
            "description": "MCP server for filesystem access",
            "dist-tags": {"latest": "1.0.0"},
            "time": {"1.0.0": "2026-07-10T00:00:00.000Z"},
            "versions": {
                "1.0.0": {
                    "name": "@modelcontextprotocol/server-example",
                    "description": "MCP server for filesystem access",
                }
            },
        },
        "https://registry.npmjs.org/@modelcontextprotocol%2Fserver-example",
        fetched_at=datetime.now(timezone.utc),
    )
    assert record is not None
    assert "New/Recently Added" in record.categories
