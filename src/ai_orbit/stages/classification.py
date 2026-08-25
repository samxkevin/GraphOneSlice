from __future__ import annotations

from datetime import datetime, timezone
import re

from src.ai_orbit.models import Entity, RawEntityRecord
from src.ai_orbit.utils.url import normalize_url

_TOPIC_TASKS = {
    "agents": "autonomous agent workflows",
    "agentic-ai": "autonomous agent workflows",
    "autonomous-agents": "autonomous agent workflows",
    "prompt-engineering": "prompt engineering",
    "prompts": "prompt engineering",
    "machine-learning": "machine learning",
    "llm": "large language model applications",
    "chatgpt": "chatbot applications",
}

_DESCRIPTION_TASKS = [
    (re.compile(r"filesystem", re.I), "filesystem access"),
    (re.compile(r"memory", re.I), "persistent memory"),
    (re.compile(r"problem solving|sequential thinking", re.I), "problem solving"),
    (re.compile(r"github api", re.I), "source code repository automation"),
]


def classify_and_create_tasks(entities: list[Entity], source_key_to_id: dict[str, str]) -> tuple[list[RawEntityRecord], dict[str, list[dict[str, str]]]]:
    """Create task entities from observed topics/descriptions.

    Returns task raw records and a map from entity id to task relationship specs.
    The task names are not invented by an LLM; each is a controlled label mapped
    from an observed source topic or phrase and is kept auditable in evidence.
    """
    task_records: dict[str, RawEntityRecord] = {}
    entity_task_edges: dict[str, list[dict[str, str]]] = {}
    now = datetime.now(timezone.utc)

    for entity in entities:
        if entity.entity_type not in {"repository", "tool", "mcp"}:
            continue
        tasks: list[tuple[str, str, str]] = []
        topics = (((entity.metadata or {}).get("repository") or {}).get("topics") or [])
        for topic in topics:
            task = _TOPIC_TASKS.get(str(topic).lower())
            if task:
                tasks.append((task, "github_topic", str(topic)))
        for pattern, task in _DESCRIPTION_TASKS:
            match = pattern.search(entity.description or "")
            if match:
                tasks.append((task, "description_phrase", match.group(0)))
        for task_name, method, observed_value in tasks[:2]:
            key = f"task:{task_name}"
            if key not in task_records:
                task_records[key] = RawEntityRecord(
                    source_key=key,
                    entity_type="task",
                    name=task_name,
                    description=f"Task label derived from observed source value: {observed_value}.",
                    url=normalize_url(entity.source.url),
                    categories=["Tasks"],
                    source_name=entity.source.name,
                    source_url=entity.source.url,
                    raw={"observed_value": observed_value, "method": method, "source_entity_id": entity.id},
                    metadata={},
                    fetched_at=now,
                )
            entity_task_edges.setdefault(entity.id, []).append({
                "task_source_key": key,
                "method": method,
                "observed_value": observed_value,
                "source_url": entity.source.url,
            })
    return list(task_records.values()), entity_task_edges
