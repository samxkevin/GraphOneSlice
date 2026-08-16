from datetime import datetime, timezone
from pathlib import Path

from src.models.schemas import EvidenceType
from src.parsers.repo_evidence_parser import extract_github_candidates, normalize_github_repo_url

FIXTURES = Path(__file__).parent / "fixtures" / "repo_evidence"
NOW = datetime.now(timezone.utc)
ABS_URL = "https://arxiv.org/abs/2508.99999"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text()


# -----------------------------------------------------------------
# A. Explicit repository link
# -----------------------------------------------------------------
def test_explicit_link_returns_exactly_one_candidate_with_full_provenance():
    html = _load("A_explicit_link.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)

    assert len(candidates) == 1
    c = candidates[0]
    assert c.repo_url == "https://github.com/openai/example-repo"
    assert c.evidence_type == EvidenceType.AUTHORITATIVE_PAPER_PAGE
    assert c.evidence_source_url == ABS_URL
    assert c.evidence_locator is not None
    assert "comments" in c.evidence_locator
    assert c.observed_at == NOW


def test_site_chrome_links_are_never_picked_up():
    # The fixture deliberately includes arXiv's own nav/footer GitHub
    # links (github.com/arXiv/arxiv-site, github.com/orgs/arxiv-community)
    # -- these must NOT appear as candidates, and the org one is also
    # structurally invalid (reserved 'orgs' owner segment).
    html = _load("A_explicit_link.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    repo_urls = {c.repo_url for c in candidates}
    assert "https://github.com/arXiv/arxiv-site" not in repo_urls
    assert not any("arxiv-community" in u for u in repo_urls)


# -----------------------------------------------------------------
# B. Multiple explicit repositories
# -----------------------------------------------------------------
def test_multiple_distinct_repos_are_all_preserved():
    html = _load("B_multiple_repos.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    repo_urls = {c.repo_url for c in candidates}
    assert repo_urls == {
        "https://github.com/labA/method-pytorch",
        "https://github.com/labB/method-jax",
    }
    # both at the same (strongest) evidence tier -- neither is dropped
    assert all(c.evidence_type == EvidenceType.AUTHORITATIVE_PAPER_PAGE for c in candidates)


# -----------------------------------------------------------------
# C. No repository
# -----------------------------------------------------------------
def test_no_repo_returns_empty_list():
    html = _load("C_no_repo.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    assert candidates == []


# -----------------------------------------------------------------
# D. Non-GitHub code link must not be coerced into a GitHub candidate
# -----------------------------------------------------------------
def test_non_github_link_is_never_converted_to_github_candidate():
    html = _load("D_non_github_link.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    assert candidates == []
    # sanity: the normalizer itself also rejects these URLs directly
    assert normalize_github_repo_url("https://gitlab.com/someorg/somerepo") is None
    assert normalize_github_repo_url("https://example-lab.org/projects/method") is None


# -----------------------------------------------------------------
# E. GitHub subpath normalization
# -----------------------------------------------------------------
def test_subpath_links_normalize_to_repository_identity():
    html = _load("E_subpath_links.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    # tree/main and blob/main/README.md both resolve to the same repo,
    # and are the SAME normalized URL -> deduplicated to one candidate
    assert len(candidates) == 1
    assert candidates[0].repo_url == "https://github.com/labC/big-repo"


def test_normalize_handles_tree_blob_git_and_trailing_slash():
    assert normalize_github_repo_url("https://github.com/org/repo/tree/main") == "https://github.com/org/repo"
    assert normalize_github_repo_url("https://github.com/org/repo/blob/main/x.py") == "https://github.com/org/repo"
    assert normalize_github_repo_url("https://github.com/org/repo.git") == "https://github.com/org/repo"
    assert normalize_github_repo_url("https://github.com/org/repo/") == "https://github.com/org/repo"


# -----------------------------------------------------------------
# F. Duplicate links (identical URL, and trailing-slash variant)
# -----------------------------------------------------------------
def test_duplicate_links_deduplicated_deterministically():
    html = _load("F_duplicate_links.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    assert len(candidates) == 1
    assert candidates[0].repo_url == "https://github.com/labD/repo-x"
    # first occurrence's locator/text is preserved (from the abstract block)
    assert candidates[0].evidence_text == "github.com/labD/repo-x"


# -----------------------------------------------------------------
# G. Malformed/invalid GitHub URLs must not create false candidates
# -----------------------------------------------------------------
def test_malformed_github_urls_produce_no_candidates():
    html = _load("G_malformed_links.html")
    candidates = extract_github_candidates(html, ABS_URL, NOW)
    assert candidates == []


def test_normalize_rejects_reserved_owner_and_ownerless_urls():
    assert normalize_github_repo_url("https://github.com/orgs/somelab") is None
    assert normalize_github_repo_url("https://github.com/") is None
    assert normalize_github_repo_url("https://github.com/justanowner") is None
    assert normalize_github_repo_url("not a url at all") is None
