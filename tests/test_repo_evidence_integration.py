from datetime import datetime, timezone
from pathlib import Path

from src.parsers.repo_evidence_parser import extract_github_candidates
from src.repo_association.associator import RepoAssociator

FIXTURES = Path(__file__).parent / "fixtures" / "repo_evidence"
NOW = datetime.now(timezone.utc)
ABS_URL = "https://arxiv.org/abs/2508.99999"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


# -----------------------------------------------------------------
# I. Full association integration: extracted evidence -> existing,
#    UNMODIFIED RepoAssociator.select_primary(). Verifies the tier
#    and selection behavior established earlier is unaffected by
#    real extraction output.
# -----------------------------------------------------------------
def test_single_explicit_link_is_selected_end_to_end():
    html = _load("A_explicit_link.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    selected = RepoAssociator().select_primary(candidates)
    assert selected is not None
    assert selected.repo_url == "https://github.com/openai/example-repo"


def test_two_repos_at_same_tier_remain_ambiguous_end_to_end():
    # Both candidates are AUTHORITATIVE_PAPER_PAGE (same evidence tier),
    # neither locator says "official" -- the associator must NOT guess.
    html = _load("B_multiple_repos.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    assert len(candidates) == 2  # extraction preserved both

    selected = RepoAssociator().select_primary(candidates)
    assert selected is None  # ambiguity preserved -- popularity/order never used as a tiebreak


def test_no_repo_page_selects_nothing_end_to_end():
    html = _load("C_no_repo.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    selected = RepoAssociator().select_primary(candidates)
    assert candidates == []
    assert selected is None


def test_deduplicated_subpath_links_select_the_single_repo_end_to_end():
    html = _load("E_subpath_links.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    selected = RepoAssociator().select_primary(candidates)
    assert selected is not None
    assert selected.repo_url == "https://github.com/labC/big-repo"
