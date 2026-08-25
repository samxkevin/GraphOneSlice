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
    (re.compile(r"filesystem access|access(?:es|ing)?[^.]{0,80}filesystem|filesystem[^.]{0,80}access", re.I), "filesystem access"),
    (re.compile(r"memory", re.I), "persistent memory"),
    (re.compile(r"problem solving|sequential thinking", re.I), "problem solving"),
    (re.compile(r"github api", re.I), "source code repository automation"),
    (re.compile(r"agentic|\bagents?\b|multi-agent", re.I), "autonomous agent workflows"),
    (re.compile(r"chatbot|\bchat\b|chatgpt|chat experiences", re.I), "chatbot applications"),
    (re.compile(r"tool-calling|tool calling", re.I), "tool calling"),
    (re.compile(r"structured-output|structured output", re.I), "structured output generation"),
    (re.compile(r"stable diffusion|comfyui|image, video & audio generation|image generation|video generation|audio generation", re.I), "creative media generation"),
    (re.compile(r"observability|instrumentation", re.I), "AI application observability"),
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
        if ((entity.metadata or {}).get("tool") or {}).get("task_mapping_allowed") is False:
            continue
        tasks: list[dict[str, str]] = []
        topics = (((entity.metadata or {}).get("repository") or {}).get("topics") or [])
        for topic in topics:
            topic_value = str(topic).lower()
            task = _TOPIC_TASKS.get(topic_value)
            if task:
                tasks.append({
                    "task_name": task,
                    "method": "github_topic",
                    "observed_value": str(topic),
                    "task_url": f"https://github.com/topics/{topic_value}",
                    "url_role": "canonical_topic_url",
                })
        for pattern, task in _DESCRIPTION_TASKS:
            match = pattern.search(entity.description or "")
            if match:
                tasks.append({
                    "task_name": task,
                    "method": "description_phrase",
                    "observed_value": match.group(0),
                    "task_url": entity.source.url,
                    "url_role": "evidence_source_url",
                })
        for task_spec in tasks[:2]:
            task_name = task_spec["task_name"]
            method = task_spec["method"]
            observed_value = task_spec["observed_value"]
            key = f"task:{task_name}"
            if key not in task_records:
                task_records[key] = RawEntityRecord(
                    source_key=key,
                    entity_type="task",
                    name=task_name,
                    description=f"Task label derived from observed source value: {observed_value}.",
                    url=normalize_url(task_spec["task_url"]),
                    categories=["Tasks"],
                    source_name=entity.source.name,
                    source_url=entity.source.url,
                    raw={"observed_value": observed_value, "method": method, "source_entity_id": entity.id},
                    metadata={
                        "task": {
                            "canonical_label": task_name,
                            "observed_value": observed_value,
                            "mapping_method": method,
                            "url_role": task_spec["url_role"],
                            "evidence_source_url": entity.source.url,
                        }
                    },
                    fetched_at=now,
                )
            entity_task_edges.setdefault(entity.id, []).append({
                "task_source_key": key,
                "method": method,
                "observed_value": observed_value,
                "source_url": entity.source.url,
            })
    return list(task_records.values()), entity_task_edges
