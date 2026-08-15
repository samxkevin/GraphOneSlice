"""
Orchestrator: wires adapter -> parser -> repo association -> github ->
validator -> storage -> exporter into a runnable pipeline. Contains no
business logic of its own -- it only sequences calls and handles the
per-record failure boundary so one bad record never kills the batch.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from src.adapters.arxiv_adapter import ArxivAdapter
from src.config.settings import Settings, get_settings
from src.exporters.sheets_exporter import SheetsExporter
from src.github_client.client import GithubClient
from src.models.schemas import FetchObservation, GithubApiStatus, RepoLinkCandidate
from src.parsers.arxiv_parser import ArxivParseError, parse_atom_feed
from src.pipeline.logging_config import configure_logging, get_logger
from src.repo_association.associator import RepoAssociator
from src.storage.db import Storage
from src.validator.validator import PaperValidationError, validate_and_build_export

logger = get_logger(__name__)


async def run_discovery_and_parse(settings: Settings, storage: Storage) -> int:
    """Stage 1+2: fetch arXiv pages, record raw evidence, parse deterministically."""
    adapter = ArxivAdapter(settings)
    observations = await adapter.discover_all()

    total_parsed = 0
    for obs_dict in observations:
        obs = FetchObservation(**obs_dict)
        await storage.record_fetch_observation(obs)

        try:
            papers = parse_atom_feed(obs.raw_payload["atom_xml"])
        except ArxivParseError as exc:
            await storage.log_event(
                stage="parse", status="ERROR", source="arxiv",
                error_type="ArxivParseError", detail={"error": str(exc)},
            )
            continue

        for parsed in papers:
            paper_id = await storage.upsert_paper_discovered(parsed)
            claimed = await storage.claim_paper(paper_id, "DISCOVERED", "FETCHED")
            if not claimed:
                # already progressed by a prior run -- fine, not an error
                continue
            await storage.mark_parsed(parsed, paper_id)
            total_parsed += 1
            await storage.log_event(
                stage="parse", status="OK", source="arxiv", record_id=paper_id,
            )
    return total_parsed


async def run_repo_resolution(settings: Settings, storage: Storage) -> None:
    """
    Stage 3: evidence-tiered repo association.

    NOTE on this first-slice scope: the arxiv_parser's
    extract_authoritative_repo_links() (abs-page scraping for an explicit
    author-provided code link) is not yet wired in -- see that module's
    docstring. Until it is, no repo candidates are generated here, so every
    paper correctly resolves with github_url=null rather than a fabricated
    or inferred association. This is intentionally conservative: the
    interface (RepoAssociator + paper_repo_links) is fully built and
    tested against synthetic candidates (see tests/), but the live
    evidence-gathering step for arXiv's own abs pages is the next piece
    of work, not a shortcut taken here.
    """
    associator = RepoAssociator()
    papers = await storage.get_papers_by_status("PARSED", settings.pipeline_batch_size)
    for paper in papers:
        paper_id = paper["id"]
        claimed = await storage.claim_paper(paper_id, "PARSED", "RESOLVING_REPO")
        if not claimed:
            continue

        candidates_raw = await storage.get_repo_candidates(paper_id)
        candidates = [
            RepoLinkCandidate(
                repo_url=c["repo_url"],
                evidence_type=c["evidence_type"],
                evidence_source_url=c["evidence_source_url"],
                evidence_locator=c["evidence_locator"],
                evidence_text=c["evidence_text"],
                association_method=c["association_method"],
                observed_at=c["observed_at"],
            )
            for c in candidates_raw
        ]
        selected = associator.select_primary(candidates)
        if selected is not None:
            match = next(c for c in candidates_raw if c["repo_url"] == selected.repo_url)
            await storage.select_repo_link(match["id"])

        await storage.claim_paper(paper_id, "RESOLVING_REPO", "RESOLVED")
        await storage.log_event(
            stage="repo_resolution", status="OK", source="arxiv", record_id=paper_id,
            detail={"candidates": len(candidates), "selected": selected.repo_url if selected else None},
        )


async def run_github_verification(settings: Settings, storage: Storage) -> None:
    """Stage 4: verify selected repos + fetch current star counts."""
    client = GithubClient(settings)
    papers = await storage.get_papers_by_status("RESOLVED", settings.pipeline_batch_size)
    for paper in papers:
        paper_id = paper["id"]
        selected = await storage.get_selected_repo_link(paper_id)
        if selected is not None:
            snapshot = await client.verify_and_get_stars(selected["repo_url"])
            await storage.record_github_snapshot(snapshot)
            await storage.log_event(
                stage="github_verify", status=snapshot.api_status.value,
                source="github", record_id=paper_id,
                detail={"repo_url": snapshot.repo_url, "stars": snapshot.stargazers_count},
            )
        # else: no repo candidate -- nothing to verify, valid outcome


async def run_validation(settings: Settings, storage: Storage) -> None:
    """Stage 5: deterministic validation -> validated_records."""
    from src.models.schemas import ParsedPaper as _ParsedPaper

    papers = await storage.get_papers_by_status("RESOLVED", settings.pipeline_batch_size)
    for paper in papers:
        paper_id = paper["id"]
        parsed = _ParsedPaper(
            arxiv_id=paper["arxiv_id"],
            canonical_url=paper["canonical_url"],
            title=paper["title"] or "",
            authors=paper["authors"] if isinstance(paper["authors"], list) else [],
            abstract=paper["abstract"],
            published_date=paper["published_date"],
        )
        selected = await storage.get_selected_repo_link(paper_id)
        snapshot = None
        if selected is not None:
            snapshot = await storage.get_latest_github_snapshot(selected["repo_url"])

        try:
            payload = validate_and_build_export(parsed, selected, snapshot)
        except PaperValidationError as exc:
            await storage.mark_failed(paper_id, exc.reason)
            await storage.log_event(
                stage="validate", status="FAILED", source="arxiv",
                record_id=paper_id, error_type="PaperValidationError",
                detail={"reason": exc.reason},
            )
            continue

        await storage.upsert_validated_record(paper_id, payload)
        await storage.claim_paper(paper_id, "RESOLVED", "VALIDATED")
        await storage.log_event(stage="validate", status="OK", source="arxiv", record_id=paper_id)


async def run_export(settings: Settings, storage: Storage) -> None:
    """Stage 6: idempotent full-tab export to Google Sheets."""
    exporter = SheetsExporter(settings)
    payloads = await storage.get_all_validated_export_payloads()
    exporter.export_all(payloads)

    unexported = await storage.get_unexported_validated_records(limit=100_000)
    await storage.mark_exported([r["id"] for r in unexported])
    await storage.log_event(
        stage="export", status="OK", source="sheets",
        detail={"rows_exported": len(payloads)},
    )


async def run_pipeline() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    storage = await Storage.create(settings.database_url, settings.db_pool_min_size, settings.db_pool_max_size)
    try:
        await storage.run_migration("src/storage/schema.sql")
        parsed_count = await run_discovery_and_parse(settings, storage)
        logger.info("discovery+parse complete", extra={"stage": "pipeline", "status": "OK",
                                                          "detail": {"parsed": parsed_count}})
        await run_repo_resolution(settings, storage)
        await run_github_verification(settings, storage)
        await run_validation(settings, storage)
        await run_export(settings, storage)
    finally:
        await storage.close()


if __name__ == "__main__":
    asyncio.run(run_pipeline())
