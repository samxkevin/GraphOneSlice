from __future__ import annotations

import asyncio
import logging
from typing import Iterable

from src.ai_orbit.adapters.ai_tools_products import AIToolsProductDirectoryAdapter
from src.ai_orbit.adapters.ai_device_catalog import AIDeviceCatalogAdapter
from src.ai_orbit.adapters.base import SourceAdapter
from src.ai_orbit.adapters.hailo_model_zoo import HailoModelZooAdapter
from src.ai_orbit.adapters.feasibility_probes import build_candidate_probe_adapters
from src.ai_orbit.adapters.jobs_personal_candidates import build_jobs_personal_probe_adapters
from src.ai_orbit.adapters.github import GitHubAdapter
from src.ai_orbit.adapters.github_releases_news import GitHubReleasesNewsAdapter
from src.ai_orbit.adapters.huggingface import HuggingFaceProbeAdapter
from src.ai_orbit.adapters.npm_mcp import NpmMcpAdapter
from src.ai_orbit.adapters.npm_search_tools import NpmSearchToolAdapter
from src.ai_orbit.adapters.models_dev_catalog import ModelsDevGitHubCatalogAdapter
from src.ai_orbit.adapters.official_sdk_models import OfficialSDKModelAdapter
from src.ai_orbit.adapters.openai_rss_probe import OpenAIRssProbeAdapter
from src.ai_orbit.adapters.pypi import PyPIPackageAdapter
from src.ai_orbit.adapters.pyvideo_videos import PyVideoVideosAdapter
from src.ai_orbit.adapters.ros_robots import RosRobotsCatalogAdapter
from src.ai_orbit.config import AIOrbitSettings, get_ai_orbit_settings
from src.ai_orbit.models import PipelineState, RawEntityRecord
from src.ai_orbit.stages.classification import classify_and_create_tasks
from src.ai_orbit.stages.cleaning import clean_records
from src.ai_orbit.stages.normalization import normalize_records
from src.ai_orbit.stages.relationships import map_relationships
from src.ai_orbit.stages.resolution import resolve_entities
from src.ai_orbit.stages.storage import write_outputs
from src.ai_orbit.stages.validation import validate_outputs
from src.pipeline.logging_config import configure_logging, get_logger

logger = get_logger(__name__)


def build_default_adapters(settings: AIOrbitSettings) -> list[SourceAdapter]:
    return [
        GitHubAdapter(settings),
        PyPIPackageAdapter(settings),
        NpmMcpAdapter(settings),
        NpmSearchToolAdapter(settings),
        OfficialSDKModelAdapter(settings),
        AIToolsProductDirectoryAdapter(settings),
        ModelsDevGitHubCatalogAdapter(settings),
        RosRobotsCatalogAdapter(settings),
        GitHubReleasesNewsAdapter(settings),
        PyVideoVideosAdapter(settings),
        AIDeviceCatalogAdapter(settings),
        HailoModelZooAdapter(settings),
        HuggingFaceProbeAdapter(settings),
        OpenAIRssProbeAdapter(settings),
        *build_candidate_probe_adapters(settings),
        *build_jobs_personal_probe_adapters(settings),
    ]


async def run_ai_orbit_pipeline(
    settings: AIOrbitSettings | None = None,
    adapters: Iterable[SourceAdapter] | None = None,
    *,
    write_files: bool = True,
) -> PipelineState:
    settings = settings or get_ai_orbit_settings()
    configure_logging(settings.log_level)
    adapter_list = list(adapters) if adapters is not None else build_default_adapters(settings)
    state = PipelineState()

    # Discovery/source verification. Each source has its own failure boundary;
    # one failing source cannot corrupt records from successful sources.
    for adapter in adapter_list:
        logger.info("verifying source", extra={"stage": "source_verification", "source": adapter.name})
        feasibility = await adapter.verify()
        state.source_feasibility.append(feasibility)
        logger.info(
            "source verification completed",
            extra={"stage": "source_verification", "source": adapter.name, "status": feasibility.status},
        )
        if feasibility.status == "unusable":
            state.source_failures.append({
                "source": adapter.name,
                "failure": feasibility.failure_behavior,
                "url": feasibility.url,
                "stage": "source_verification",
            })
            continue
        try:
            records = await adapter.discover()
            state.raw_records.extend(records)
            feasibility.yielded_usable_records = len(records)
            logger.info(
                "source discovery completed",
                extra={"stage": "discovery", "source": adapter.name, "status": "OK", "record_id": len(records)},
            )
        except Exception as exc:  # noqa: BLE001 - source isolation boundary
            state.source_failures.append({
                "source": adapter.name,
                "failure": f"{type(exc).__name__}: {exc}",
                "stage": "discovery",
            })
            logger.warning(
                "source discovery failed",
                extra={"stage": "discovery", "source": adapter.name, "status": "ERROR", "error_type": type(exc).__name__},
            )

    state.metrics["total_discovered"] = len(state.raw_records)
    state.metrics["total_extracted"] = len(state.raw_records)

    state.cleaned_records = clean_records(state.raw_records)
    state.metrics["total_cleaned"] = len(state.cleaned_records)

    state.candidates = normalize_records(state.cleaned_records)
    state.metrics["total_normalized"] = len(state.candidates)

    entities, mapping_log, source_key_to_id, _source_key_to_canonical, duplicate_count = resolve_entities(state.candidates)
    state.entities = entities
    state.mapping_log = mapping_log
    state.metrics["duplicate_candidates"] = duplicate_count

    task_records, task_edge_specs = classify_and_create_tasks(state.entities, source_key_to_id)
    if task_records:
        task_cleaned = clean_records(task_records)
        task_candidates = normalize_records(task_cleaned)
        task_entities, task_mapping, task_source_key_to_id, _task_canonical, task_duplicates = resolve_entities(task_candidates)
        # Merge task entities with existing by id; task resolver only sees tasks,
        # so id collisions are unlikely but kept deterministic.
        existing_ids = {entity.id for entity in state.entities}
        for entity in task_entities:
            if entity.id not in existing_ids:
                state.entities.append(entity)
                existing_ids.add(entity.id)
        state.mapping_log.extend(task_mapping)
        source_key_to_id.update(task_source_key_to_id)
        state.cleaned_records.extend(task_cleaned)
        state.candidates.extend(task_candidates)
        state.metrics["total_cleaned"] = len(state.cleaned_records)
        state.metrics["total_normalized"] = len(state.candidates)
        state.metrics["classification_generated_tasks"] = len(task_records)
        state.metrics["duplicate_candidates"] += task_duplicates

    state.relationships = map_relationships(state.cleaned_records, state.entities, source_key_to_id, task_edge_specs)

    source_feasibility_payload = [entry.model_dump(mode="json") for entry in state.source_feasibility]
    valid_entities, valid_relationships, validation_report = validate_outputs(
        state.entities,
        state.relationships,
        metrics=state.metrics,
        source_failures=state.source_failures,
        source_feasibility=source_feasibility_payload,
        rejected_records=state.rejected_records,
    )
    state.entities = valid_entities
    state.relationships = valid_relationships
    state.metrics["validation_status"] = validation_report["status"]

    if write_files:
        write_outputs(
            settings.output_dir,
            entities=state.entities,
            relationships=state.relationships,
            mapping_log=state.mapping_log,
            validation_report=validation_report,
            source_feasibility=state.source_feasibility,
        )
        logger.info(
            "AI Orbit pipeline outputs written",
            extra={"stage": "storage", "status": validation_report["status"], "record_id": len(state.entities)},
        )

    return state


def main() -> None:
    asyncio.run(run_ai_orbit_pipeline())


if __name__ == "__main__":
    main()
