"""
Deterministic parser: arXiv Atom XML -> ParsedPaper.

Per the assessment's own LLM-placement principle, arXiv already supplies
title/authors/date/URL as structured metadata -- an LLM must not be used
here. This module is pure, synchronous, and side-effect free so it can
be unit tested against saved fixtures without network access.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from pydantic import ValidationError

from src.models.schemas import ParsedPaper

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


class ArxivParseError(Exception):
    pass


def _extract_arxiv_id(id_url: str) -> str:
    """arXiv <id> looks like 'http://arxiv.org/abs/2508.01234v1'.
    We strip the version suffix so the canonical identity is stable
    across revisions of the same paper."""
    match = re.search(r"abs/([^v]+)", id_url)
    if not match:
        raise ArxivParseError(f"could not extract arxiv_id from '{id_url}'")
    return match.group(1)


def parse_entry(entry: ET.Element) -> ParsedPaper:
    id_el = entry.find(f"{ATOM_NS}id")
    title_el = entry.find(f"{ATOM_NS}title")
    summary_el = entry.find(f"{ATOM_NS}summary")
    published_el = entry.find(f"{ATOM_NS}published")

    if id_el is None or id_el.text is None:
        raise ArxivParseError("entry missing <id>")
    if title_el is None or title_el.text is None:
        raise ArxivParseError("entry missing <title>")

    arxiv_id = _extract_arxiv_id(id_el.text.strip())
    canonical_url = f"https://arxiv.org/abs/{arxiv_id}"

    authors = []
    for author_el in entry.findall(f"{ATOM_NS}author"):
        name_el = author_el.find(f"{ATOM_NS}name")
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    published_date = None
    if published_el is not None and published_el.text:
        # arXiv format: 2026-08-01T12:34:56Z
        published_date = datetime.strptime(
            published_el.text.strip(), "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)

    title = re.sub(r"\s+", " ", title_el.text).strip()
    abstract = re.sub(r"\s+", " ", summary_el.text).strip() if summary_el is not None and summary_el.text else None

    return ParsedPaper(
        arxiv_id=arxiv_id,
        canonical_url=canonical_url,
        title=title,
        authors=authors,
        abstract=abstract,
        published_date=published_date,
    )


def parse_atom_feed(atom_xml: str) -> list[ParsedPaper]:
    """Parses a full Atom feed page into a list of ParsedPaper.
    Individual malformed entries are skipped (logged by the caller),
    not allowed to fail the whole page."""
    try:
        root = ET.fromstring(atom_xml)
    except ET.ParseError as exc:
        raise ArxivParseError(f"malformed Atom XML: {exc}") from exc

    papers: list[ParsedPaper] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        try:
            papers.append(parse_entry(entry))
        except (ArxivParseError, ValidationError):
            # one bad/incomplete entry (missing id, empty authors, etc.)
            # must not kill the rest of the page -- skip and continue.
            continue
    return papers


def extract_authoritative_repo_links(entry_atom_xml_fragment: str, arxiv_abs_url: str) -> list[str]:
    """
    arXiv's own Atom entries do not carry a structured GitHub-link field.
    This function is a placeholder for the (separate, explicit) step of
    fetching the arXiv abs page HTML and looking for an explicit,
    author-provided code link (e.g. a 'Code' badge / journal-ref link).
    It intentionally does NOT do title-similarity or org-name guessing --
    see repo_association/associator.py for the evidence policy.
    Not wired into the discovery loop in this first slice; returns []
    until the abs-page-scraping step is implemented.
    """
    return []
