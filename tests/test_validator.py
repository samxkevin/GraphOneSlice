from datetime import datetime, timezone

import pytest

from src.models.schemas import GithubApiStatus, ParsedPaper
from src.validator.validator import PaperValidationError, validate_and_build_export

NOW = datetime.now(timezone.utc)


def _paper(**overrides) -> ParsedPaper:
    base = dict(
        arxiv_id="2508.01234",
        canonical_url="https://arxiv.org/abs/2508.01234",
        title="A Study of Something",
        authors=["Jane Doe"],
        abstract="abstract text",
        published_date=NOW,
    )
    base.update(overrides)
    return ParsedPaper(**base)


def test_no_repo_candidate_yields_null_github_fields():
    # Outcome class: paper with no repository -- a valid, successful outcome
    payload = validate_and_build_export(_paper(), selected_repo=None, github_snapshot=None)
    assert payload["github_url"] is None
    assert payload["github_stars"] is None


def test_verified_repo_populates_url_and_stars():
    # Outcome class: successfully resolved + verified GitHub repository
    selected_repo = {"repo_url": "https://github.com/org/repo", "evidence_type": "authoritative_paper_page"}
    snapshot = {
        "exists_verified": True,
        "api_status": GithubApiStatus.OK.value,
        "stargazers_count": 1234,
        "stars_fetched_at": NOW,
    }
    payload = validate_and_build_export(_paper(), selected_repo, snapshot)
    assert payload["github_url"] == "https://github.com/org/repo"
    assert payload["github_stars"] == 1234
    assert payload["github_stars_fetched_at"] is not None
    assert payload["github_evidence_type"] == "authoritative_paper_page"


def test_deleted_repo_yields_null_not_stale_data():
    # Outcome class: unavailable/deleted GitHub repository (404 at verification time)
    selected_repo = {"repo_url": "https://github.com/org/gone", "evidence_type": "trusted_metadata"}
    snapshot = {
        "exists_verified": False,
        "api_status": GithubApiStatus.NOT_FOUND.value,
        "stargazers_count": None,
        "stars_fetched_at": NOW,
    }
    payload = validate_and_build_export(_paper(), selected_repo, snapshot)
    assert payload["github_url"] is None
    assert payload["github_stars"] is None


def test_rate_limited_snapshot_yields_null_not_guessed_stars():
    # Outcome class: retry/rate-limit path -- must never fabricate a star count
    selected_repo = {"repo_url": "https://github.com/org/repo", "evidence_type": "trusted_metadata"}
    snapshot = {
        "exists_verified": False,
        "api_status": GithubApiStatus.RATE_LIMITED.value,
        "stargazers_count": None,
        "stars_fetched_at": NOW,
    }
    payload = validate_and_build_export(_paper(), selected_repo, snapshot)
    assert payload["github_url"] is None
    assert payload["github_stars"] is None


def test_empty_title_fails_validation_explicitly():
    # Outcome class: validation failure path -- must raise, not silently drop
    paper = _paper(title="   ")
    with pytest.raises(PaperValidationError):
        validate_and_build_export(paper, None, None)


def test_no_authors_fails_at_parsed_paper_construction():
    with pytest.raises(Exception):
        ParsedPaper(
            arxiv_id="2508.01234", canonical_url="https://arxiv.org/abs/2508.01234",
            title="Title", authors=[], abstract=None, published_date=NOW,
        )
