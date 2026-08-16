"""
Storage layer. This is the ONLY module that touches the database directly.
All writes are either append-only (fetch_observations, github_repo_snapshots,
pipeline_log) or use conflict-safe / atomic-claim patterns so concurrent
workers and reruns never corrupt state or silently duplicate records.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from src.models.schemas import (
    FetchObservation,
    GithubSnapshot,
    ParsedPaper,
    RepoLinkCandidate,
)


class Storage:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    @classmethod
    async def create(cls, dsn: str, min_size: int, max_size: int) -> "Storage":
        pool = await asyncpg.create_pool(dsn=dsn, min_size=min_size, max_size=max_size)
        return cls(pool)

    async def close(self) -> None:
        await self._pool.close()

    async def run_migration(self, sql_path: str) -> None:
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()
        async with self._pool.acquire() as conn:
            await conn.execute(sql)

    # -----------------------------------------------------------
    # fetch_observations -- append-only, never overwritten
    # -----------------------------------------------------------
    async def record_fetch_observation(
        self, obs: FetchObservation, paper_id: UUID | None = None
    ) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO fetch_observations
                    (paper_id, source_name, source_url, raw_payload,
                     content_hash, fetched_at, http_status, fetch_status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                paper_id,
                obs.source_name,
                obs.source_url,
                json.dumps(obs.raw_payload),
                obs.content_hash,
                obs.fetched_at,
                obs.http_status,
                obs.fetch_status.value,
            )
            return row["id"]

    async def link_paper_to_observation(self, paper_id: UUID, fetch_observation_id: UUID) -> None:
        """Associates a paper with the (possibly-shared) fetch_observation
        that supplied its raw data, after the paper's identity is known.
        Idempotent: the composite primary key makes reruns a safe no-op,
        never a duplicate row and never a misattribution -- linking is by
        explicit id, not by URL matching."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO paper_fetch_observations (paper_id, fetch_observation_id)
                VALUES ($1, $2)
                ON CONFLICT (paper_id, fetch_observation_id) DO NOTHING
                """,
                paper_id,
                fetch_observation_id,
            )

    async def get_observations_for_paper(self, paper_id: UUID) -> list[dict[str, Any]]:
        """Returns every fetch_observation linked to a paper -- either via
        the direct scalar paper_id (1:1 fetches, e.g. abs-page HTML) or via
        the paper_fetch_observations join table (shared page fetches, e.g.
        arXiv Atom discovery). Used by tests/audits to verify lineage."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT fo.* FROM fetch_observations fo
                WHERE fo.paper_id = $1
                UNION
                SELECT fo.* FROM fetch_observations fo
                JOIN paper_fetch_observations pfo ON pfo.fetch_observation_id = fo.id
                WHERE pfo.paper_id = $1
                ORDER BY fetched_at
                """,
                paper_id,
            )
            return [dict(r) for r in rows]

    # -----------------------------------------------------------
    # papers -- logical identity, conflict-safe insert, atomic claims
    # -----------------------------------------------------------
    async def upsert_paper_discovered(self, parsed: ParsedPaper) -> UUID:
        """Insert if new; if it already exists, just bump last_seen_at.
        Never overwrites parsed fields here -- that happens explicitly
        in mark_parsed so we don't silently clobber prior state."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO papers (arxiv_id, canonical_url, status)
                VALUES ($1, $2, 'DISCOVERED')
                ON CONFLICT (arxiv_id) DO UPDATE
                    SET last_seen_at = now()
                RETURNING id
                """,
                parsed.arxiv_id,
                parsed.canonical_url,
            )
            return row["id"]

    async def claim_paper(self, paper_id: UUID, expected_status: str, new_status: str) -> bool:
        """Atomic claim: only succeeds if the paper is still in expected_status.
        Prevents races between concurrent workers on the same record."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE papers
                SET status = $3, updated_at = now()
                WHERE id = $1 AND status = $2
                RETURNING id
                """,
                paper_id,
                expected_status,
                new_status,
            )
            return row is not None

    async def mark_parsed(self, parsed: ParsedPaper, paper_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE papers
                SET title = $2, authors = $3, abstract = $4,
                    published_date = $5, status = 'PARSED', updated_at = now()
                WHERE id = $1
                """,
                paper_id,
                parsed.title,
                json.dumps(parsed.authors),
                parsed.abstract,
                parsed.published_date,
            )

    async def mark_failed(self, paper_id: UUID, reason: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE papers
                SET status = 'FAILED', failure_reason = $2, updated_at = now()
                WHERE id = $1
                """,
                paper_id,
                reason,
            )

    async def get_papers_by_status(self, status: str, limit: int) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM papers WHERE status = $1 ORDER BY first_seen_at LIMIT $2",
                status,
                limit,
            )
            return [dict(r) for r in rows]

    async def get_paper(self, paper_id: UUID) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM papers WHERE id = $1", paper_id)
            return dict(row) if row else None

    # -----------------------------------------------------------
    # paper_repo_links -- 0..N candidates, at most one selected
    # -----------------------------------------------------------
    async def add_repo_candidate(self, paper_id: UUID, candidate: RepoLinkCandidate) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO paper_repo_links
                    (paper_id, repo_url, evidence_type, evidence_strength,
                     evidence_source_url, evidence_locator, evidence_text,
                     association_method, observed_at, is_selected)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, FALSE)
                RETURNING id
                """,
                paper_id,
                candidate.repo_url,
                candidate.evidence_type.value,
                candidate.evidence_strength,
                candidate.evidence_source_url,
                candidate.evidence_locator,
                candidate.evidence_text,
                candidate.association_method.value,
                candidate.observed_at,
            )
            return row["id"]

    async def select_repo_link(self, link_id: UUID) -> None:
        """Marks exactly one link selected. The partial unique index
        (one_selected_repo_per_paper) guarantees this can't double-select."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE paper_repo_links SET is_selected = TRUE WHERE id = $1",
                link_id,
            )

    async def get_repo_candidates(self, paper_id: UUID) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM paper_repo_links WHERE paper_id = $1 ORDER BY evidence_strength ASC",
                paper_id,
            )
            return [dict(r) for r in rows]

    async def get_selected_repo_link(self, paper_id: UUID) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM paper_repo_links WHERE paper_id = $1 AND is_selected LIMIT 1",
                paper_id,
            )
            return dict(row) if row else None

    # -----------------------------------------------------------
    # github_repo_snapshots -- append-only verification history
    # -----------------------------------------------------------
    async def record_github_snapshot(self, snapshot: GithubSnapshot) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO github_repo_snapshots
                    (repo_url, exists_verified, stargazers_count, stars_fetched_at, api_status)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                snapshot.repo_url,
                snapshot.exists_verified,
                snapshot.stargazers_count,
                snapshot.stars_fetched_at,
                snapshot.api_status.value,
            )
            return row["id"]

    async def get_latest_github_snapshot(self, repo_url: str) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM github_repo_snapshots
                WHERE repo_url = $1
                ORDER BY stars_fetched_at DESC LIMIT 1
                """,
                repo_url,
            )
            return dict(row) if row else None

    # -----------------------------------------------------------
    # validated_records -- frozen export payload
    # -----------------------------------------------------------
    async def upsert_validated_record(
        self, paper_id: UUID, export_payload: dict[str, Any]
    ) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO validated_records (paper_id, export_payload, validated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (paper_id) DO UPDATE
                    SET export_payload = $2, validated_at = now(), exported_at = NULL
                RETURNING id
                """,
                paper_id,
                json.dumps(export_payload),
            )
            return row["id"]

    async def get_unexported_validated_records(self, limit: int) -> list[dict[str, Any]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM validated_records
                WHERE exported_at IS NULL
                ORDER BY validated_at
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]

    async def mark_exported(self, record_ids: list[UUID]) -> None:
        if not record_ids:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE validated_records SET exported_at = now() WHERE id = ANY($1::uuid[])",
                record_ids,
            )

    async def get_all_validated_export_payloads(self) -> list[dict[str, Any]]:
        """Used for a full idempotent re-export of the whole tab."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT export_payload FROM validated_records ORDER BY validated_at"
            )
            return [json.loads(r["export_payload"]) if isinstance(r["export_payload"], str)
                    else r["export_payload"] for r in rows]

    # -----------------------------------------------------------
    # pipeline_log -- structured, queryable log
    # -----------------------------------------------------------
    async def log_event(
        self,
        stage: str,
        status: str,
        source: str | None = None,
        record_id: UUID | None = None,
        attempt: int | None = None,
        latency_ms: int | None = None,
        error_type: str | None = None,
        provider: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO pipeline_log
                    (ts, stage, source, record_id, status, attempt,
                     latency_ms, error_type, provider, detail)
                VALUES (now(), $1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                stage,
                source,
                record_id,
                status,
                attempt,
                latency_ms,
                error_type,
                provider,
                json.dumps(detail) if detail else None,
            )
