from datetime import datetime, timezone

from src.models.schemas import AssociationMethod, EvidenceType, RepoLinkCandidate
from src.repo_association.associator import RepoAssociator

NOW = datetime.now(timezone.utc)


def _candidate(repo_url: str, evidence_type: EvidenceType, locator: str | None = None) -> RepoLinkCandidate:
    return RepoLinkCandidate(
        repo_url=repo_url,
        evidence_type=evidence_type,
        evidence_source_url="https://arxiv.org/abs/2508.01234",
        evidence_locator=locator,
        evidence_text=None,
        association_method=AssociationMethod.EXPLICIT_LINK_PARSED,
        observed_at=NOW,
    )


def test_no_candidates_returns_none():
    # Outcome class: paper with no repository
    result = RepoAssociator().select_primary([])
    assert result is None


def test_single_strong_candidate_is_selected():
    # Outcome class: paper with explicit GitHub link (single, unambiguous)
    c = _candidate("https://github.com/org/repo", EvidenceType.AUTHORITATIVE_PAPER_PAGE)
    result = RepoAssociator().select_primary([c])
    assert result is not None
    assert result.repo_url == "https://github.com/org/repo"


def test_strongest_tier_wins_over_weaker_tier():
    strong = _candidate("https://github.com/org/strong", EvidenceType.AUTHORITATIVE_PAPER_PAGE)
    weak = _candidate("https://github.com/org/weak", EvidenceType.PWC_AI_AGENT_PARSED)
    result = RepoAssociator().select_primary([weak, strong])
    assert result.repo_url == "https://github.com/org/strong"


def test_ambiguous_tie_at_same_tier_selects_nothing():
    # Outcome class: paper with multiple repository candidates, genuinely ambiguous
    a = _candidate("https://github.com/org/a", EvidenceType.TRUSTED_METADATA)
    b = _candidate("https://github.com/org/b", EvidenceType.TRUSTED_METADATA)
    result = RepoAssociator().select_primary([a, b])
    assert result is None  # ambiguity preserved, NOT resolved by any tiebreak


def test_explicit_official_label_breaks_tie_when_present_in_evidence():
    a = _candidate("https://github.com/org/mirror", EvidenceType.TRUSTED_METADATA)
    b = _candidate(
        "https://github.com/org/official", EvidenceType.TRUSTED_METADATA,
        locator="labeled 'official implementation' on the metadata page",
    )
    result = RepoAssociator().select_primary([a, b])
    assert result.repo_url == "https://github.com/org/official"


def test_never_uses_stars_or_popularity_as_tiebreak():
    # There is no stars field on RepoLinkCandidate at all -- this test
    # documents that constraint structurally: the associator cannot
    # possibly consult popularity because the model doesn't expose it.
    a = _candidate("https://github.com/org/a", EvidenceType.PWC_VERIFIED)
    b = _candidate("https://github.com/org/b", EvidenceType.PWC_VERIFIED)
    assert not hasattr(a, "stargazers_count")
    assert not hasattr(a, "stars")
    result = RepoAssociator().select_primary([a, b])
    assert result is None
