"""
Deterministic extraction of explicit GitHub repository links from an
arXiv abstract-page HTML document.

This module is pure and synchronous -- no network I/O -- so it can be
unit tested against saved HTML fixtures. Fetching the page is a separate
concern, handled by src/adapters/repo_evidence_adapter.py.

EVIDENCE POLICY (unchanged from repo_association/associator.py):
  - Only links that are explicitly PRESENT on the paper's own abs page
    are extracted. Nothing is inferred from title, authors, or search.
  - A link is only treated as evidence if it appears inside a recognized
    "content" region of the page (the abstract block, the paper's
    comments/journal-ref metadata, or an explicit code/links list),
    NOT arbitrary site chrome (nav bar, footer, "Follow us" links) --
    this avoids misattributing arXiv's own GitHub presence to the paper.
  - Every extracted link becomes a RepoLinkCandidate at
    EvidenceType.AUTHORITATIVE_PAPER_PAGE (the strongest tier) because
    it was read directly from the paper's own authoritative page.
  - Non-GitHub links (GitLab, Bitbucket, personal project pages) are
    NEVER silently converted into a GitHub candidate.
  - Duplicate links to the same repository are deduplicated, keeping the
    first (topmost) occurrence's evidence text/locator.

KNOWN LIMITATION (stated honestly, not glossed over): the container
selectors below (`_CONTENT_CONTAINER_SELECTORS`) are a best-effort
approximation of arXiv's actual abs-page DOM structure based on its
documented public layout conventions, not a live-verified scrape at
the time of writing. This must be spot-checked against real, currently
served arXiv HTML before being relied on for production coverage
numbers -- see README "Known gaps".
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from src.models.schemas import AssociationMethod, EvidenceType, RepoLinkCandidate

# Only look for evidence inside these regions of the page, to avoid
# picking up arXiv's own site-wide GitHub links (nav/footer/"Follow us").
_CONTENT_CONTAINER_SELECTORS = [
    "blockquote.abstract",       # the abstract text block
    "td.tablecell.comments",     # author-supplied "Comments" field (often has code links)
    "td.tablecell.jref",         # journal-ref field
    ".extra-services",           # arXiv's "Code, Data, Media" services block
    ".full-text-links",          # alternate arXiv link-list block
]

# github.com path segments that are platform pages, not a repo owner.
_RESERVED_OWNERS = {
    "orgs", "sponsors", "about", "features", "marketplace", "topics",
    "search", "settings", "apps", "collections", "events", "pricing",
    "security", "site", "support", "trending", "explore", "notifications",
    "login", "join", "contact", "enterprise", "customer-stories",
    "readme", "copilot", "pulls", "issues", "notices", "government",
}


def normalize_github_repo_url(url: str) -> str | None:
    """
    Normalizes a GitHub URL to its canonical repository identity
    (https://github.com/{owner}/{repo}), or returns None if the URL is
    not a GitHub URL, or is a GitHub URL that doesn't identify a
    specific repository (e.g. github.com/topics/ai, github.com/orgs/foo).

    Handles subpaths deterministically:
      https://github.com/org/repo/tree/main       -> https://github.com/org/repo
      https://github.com/org/repo/blob/main/x.py  -> https://github.com/org/repo
      https://github.com/org/repo.git              -> https://github.com/org/repo
      https://github.com/org/repo/                 -> https://github.com/org/repo
    """
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None

    host = (parsed.netloc or "").lower()
    if host not in ("github.com", "www.github.com"):
        return None

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None  # no repo identified, e.g. github.com/ or github.com/someowner

    owner, repo = parts[0], parts[1]
    if owner.lower() in _RESERVED_OWNERS:
        return None

    repo = repo.removesuffix(".git")
    if not repo:
        return None

    return f"https://github.com/{owner}/{repo}"


def _find_content_containers(soup: BeautifulSoup) -> list[Tag]:
    containers: list[Tag] = []
    for selector in _CONTENT_CONTAINER_SELECTORS:
        containers.extend(soup.select(selector))
    return containers


def extract_github_candidates(
    html: str,
    arxiv_abs_url: str,
    observed_at: datetime,
) -> list[RepoLinkCandidate]:
    """
    Pure function: HTML string -> deduplicated list of RepoLinkCandidate.
    Returns [] if no explicit GitHub link is found in a recognized
    content region -- a valid, successful (conservative) outcome.
    """
    soup = BeautifulSoup(html, "html.parser")
    containers = _find_content_containers(soup)
    if not containers:
        return []

    seen_repo_urls: set[str] = set()
    candidates: list[RepoLinkCandidate] = []

    for container in containers:
        for anchor in container.find_all("a", href=True):
            href = anchor["href"]
            normalized = normalize_github_repo_url(href)
            if normalized is None:
                continue  # not a GitHub repo link -- never guessed, never coerced
            if normalized in seen_repo_urls:
                continue  # duplicate occurrence of an already-captured repo -- skip
            seen_repo_urls.add(normalized)

            anchor_text = anchor.get_text(strip=True) or None
            locator = f"<a> in {_describe_container(container)}"
            if anchor_text:
                locator += f", text='{anchor_text}'"

            candidates.append(
                RepoLinkCandidate(
                    repo_url=normalized,
                    evidence_type=EvidenceType.AUTHORITATIVE_PAPER_PAGE,
                    evidence_source_url=arxiv_abs_url,
                    evidence_locator=locator,
                    evidence_text=anchor_text,
                    association_method=AssociationMethod.EXPLICIT_LINK_PARSED,
                    observed_at=observed_at,
                )
            )

    return candidates


def _describe_container(container: Tag) -> str:
    classes = container.get("class")
    class_str = ".".join(classes) if classes else ""
    return f"{container.name}.{class_str}" if class_str else container.name
