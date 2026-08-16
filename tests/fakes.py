"""
In-memory fake implementing the subset of Storage's public interface used
by the orchestrator, for testing lineage/provenance logic without a live
Postgres connection. Mirrors the REAL semantics that matter for these
tests -- notably: fetch_observations is append-only, paper identity is
deduplicated by arxiv_id, and paper_fetch_observations linking is
idempotent (a set, matching the real composite-primary-key ON CONFLICT
DO NOTHING behavior) -- not a full reimplementation of storage/db.py.
"""
from __future__ import annotations

import itertools
from typing import Any
from uuid import UUID, uuid4


class FakeStorage:
    def __init__(self) -> None:
        self.fetch_observations: dict[UUID, dict[str, Any]] = {}
        self.papers: dict[UUID, dict[str, Any]] = {}
        self._arxiv_id_to_paper_id: dict[str, UUID] = {}
        self.paper_fetch_observations: set[tuple[UUID, UUID]] = set()
        self.repo_candidates: dict[UUID, dict[str, Any]] = {}  # candidate_id -> row
        self.log_events: list[dict[str, Any]] = []

    # -----------------------------------------------------------
    # fetch_observations -- append-only, exactly like the real table
    # -----------------------------------------------------------
    async def record_fetch_observation(self, obs, paper_id: UUID | None = None) -> UUID:
        obs_id = uuid4()
        self.fetch_observations[obs_id] = {
            "id": obs_id,
            "paper_id": paper_id,
            "source_name": obs.source_name,
            "source_url": obs.source_url,
            "raw_payload": obs.raw_payload,
            "content_hash": obs.content_hash,
            "fetched_at": obs.fetched_at,
            "http_status": obs.http_status,
            "fetch_status": obs.fetch_status.value if hasattr(obs.fetch_status, "value") else obs.fetch_status,
        }
        return obs_id

    async def link_paper_to_observation(self, paper_id: UUID, fetch_observation_id: UUID) -> None:
        # set semantics == ON CONFLICT (paper_id, fetch_observation_id) DO NOTHING
        self.paper_fetch_observations.add((paper_id, fetch_observation_id))

    async def get_observations_for_paper(self, paper_id: UUID) -> list[dict[str, Any]]:
        direct = [o for o in self.fetch_observations.values() if o["paper_id"] == paper_id]
        via_join = [
            self.fetch_observations[obs_id]
            for (pid, obs_id) in self.paper_fetch_observations
            if pid == paper_id
        ]
        seen_ids = set()
        result = []
        for o in direct + via_join:
            if o["id"] not in seen_ids:
                seen_ids.add(o["id"])
                result.append(o)
        return sorted(result, key=lambda o: o["fetched_at"])

    # -----------------------------------------------------------
    # papers
    # -----------------------------------------------------------
    async def upsert_paper_discovered(self, parsed) -> UUID:
        existing = self._arxiv_id_to_paper_id.get(parsed.arxiv_id)
        if existing is not None:
            return existing
        paper_id = uuid4()
        self._arxiv_id_to_paper_id[parsed.arxiv_id] = paper_id
        self.papers[paper_id] = {
            "id": paper_id,
            "arxiv_id": parsed.arxiv_id,
            "canonical_url": parsed.canonical_url,
            "status": "DISCOVERED",
            "title": None,
            "authors": None,
            "abstract": None,
            "published_date": None,
        }
        return paper_id

    async def claim_paper(self, paper_id: UUID, expected_status: str, new_status: str) -> bool:
        paper = self.papers[paper_id]
        if paper["status"] != expected_status:
            return False
        paper["status"] = new_status
        return True

    async def mark_parsed(self, parsed, paper_id: UUID) -> None:
        paper = self.papers[paper_id]
        paper["title"] = parsed.title
        paper["authors"] = parsed.authors
        paper["abstract"] = parsed.abstract
        paper["published_date"] = parsed.published_date
        paper["status"] = "PARSED"

    async def mark_failed(self, paper_id: UUID, reason: str) -> None:
        self.papers[paper_id]["status"] = "FAILED"
        self.papers[paper_id]["failure_reason"] = reason

    async def get_papers_by_status(self, status: str, limit: int) -> list[dict[str, Any]]:
        return [p for p in self.papers.values() if p["status"] == status][:limit]

    async def get_paper(self, paper_id: UUID) -> dict[str, Any] | None:
        return self.papers.get(paper_id)

    # -----------------------------------------------------------
    # paper_repo_links
    # -----------------------------------------------------------
    async def add_repo_candidate(self, paper_id: UUID, candidate) -> UUID:
        link_id = uuid4()
        self.repo_candidates[link_id] = {
            "id": link_id,
            "paper_id": paper_id,
            "repo_url": candidate.repo_url,
            "evidence_type": candidate.evidence_type.value,
            "evidence_strength": candidate.evidence_strength,
            "evidence_source_url": candidate.evidence_source_url,
            "evidence_locator": candidate.evidence_locator,
            "evidence_text": candidate.evidence_text,
            "association_method": candidate.association_method.value,
            "observed_at": candidate.observed_at,
            "is_selected": False,
        }
        return link_id

    async def select_repo_link(self, link_id: UUID) -> None:
        self.repo_candidates[link_id]["is_selected"] = True

    async def get_repo_candidates(self, paper_id: UUID) -> list[dict[str, Any]]:
        return [c for c in self.repo_candidates.values() if c["paper_id"] == paper_id]

    async def get_selected_repo_link(self, paper_id: UUID) -> dict[str, Any] | None:
        for c in self.repo_candidates.values():
            if c["paper_id"] == paper_id and c["is_selected"]:
                return c
        return None

    # -----------------------------------------------------------
    # logging (no-op storage, just recorded for optional assertions)
    # -----------------------------------------------------------
    async def log_event(self, **kwargs) -> None:
        self.log_events.append(kwargs)
