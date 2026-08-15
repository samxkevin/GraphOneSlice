"""
Deterministic validation. No LLM involved -- everything here is checkable
by plain code, per guardrails §24. Produces the frozen export_payload
that the Sheets exporter reads verbatim.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from src.models.schemas import GithubApiStatus, ParsedPaper, ResearchPaperExport


class PaperValidationError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def validate_and_build_export(
    parsed: ParsedPaper,
    selected_repo: dict[str, Any] | None,
    github_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    selected_repo: the paper_repo_links row marked is_selected=True, or None.
    github_snapshot: the latest github_repo_snapshots row for that repo, or None.

    Rules:
      - github_url is populated ONLY if a repo was selected AND its latest
        snapshot has exists_verified=True.
      - github_stars is populated ONLY if api_status == 'OK'; a stale,
        rate-limited, or not-found snapshot yields null, never a guess.
      - Missing repo association is a valid, successful outcome, not a failure.
    """
    if not parsed.title or not parsed.title.strip():
        raise PaperValidationError("empty title")
    if not parsed.authors:
        raise PaperValidationError("no authors")
    if not parsed.arxiv_id:
        raise PaperValidationError("missing arxiv_id")

    github_url = None
    github_stars = None
    stars_fetched_at = None
    evidence_type = None

    if selected_repo is not None and github_snapshot is not None:
        if github_snapshot.get("exists_verified") and github_snapshot.get("api_status") == GithubApiStatus.OK.value:
            github_url = selected_repo["repo_url"]
            github_stars = github_snapshot.get("stargazers_count")
            fetched_at = github_snapshot.get("stars_fetched_at")
            stars_fetched_at = fetched_at.isoformat() if isinstance(fetched_at, datetime) else fetched_at
            evidence_type = selected_repo.get("evidence_type")
        # else: repo candidate existed but couldn't be verified (404/rate-limited/error)
        # -> correctly left as null, not treated as a validation failure.

    try:
        export = ResearchPaperExport(
            source_url=parsed.canonical_url,
            title=parsed.title,
            authors=parsed.authors,
            paper_url=parsed.canonical_url,
            github_url=github_url,
            github_stars=github_stars,
            published_date=parsed.published_date.isoformat() if parsed.published_date else None,
            collectedAt=datetime.now(timezone.utc).isoformat(),
            github_stars_fetched_at=stars_fetched_at,
            github_evidence_type=evidence_type,
        )
    except ValidationError as exc:
        raise PaperValidationError(f"schema validation failed: {exc}") from exc

    return export.model_dump()
