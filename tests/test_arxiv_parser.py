from pathlib import Path

import pytest

from src.parsers.arxiv_parser import ArxivParseError, parse_atom_feed, parse_entry
from xml.etree import ElementTree as ET

FIXTURE = Path(__file__).parent / "fixtures" / "arxiv_sample.xml"


def test_parse_atom_feed_skips_malformed_entry_but_keeps_valid_ones():
    xml = FIXTURE.read_text()
    papers = parse_atom_feed(xml)
    # Fixture has 3 entries: 1 valid, 1 with no <author> elements (fails
    # ParsedPaper's non-empty-authors validation), 1 missing <id> entirely
    # (fails at parse_entry). Both invalid entries must be skipped
    # independently without crashing the page -- only 1 survives.
    assert len(papers) == 1


def test_arxiv_id_strips_version_suffix():
    xml = FIXTURE.read_text()
    papers = parse_atom_feed(xml)
    ids = {p.arxiv_id for p in papers}
    assert "2508.01234" in ids  # v2 suffix stripped
    # 2508.05678 is dropped (no authors), NOT because of id stripping --
    # covered separately in test_entry_with_no_authors_raises_and_is_skipped_at_feed_level


def test_title_whitespace_normalized():
    xml = FIXTURE.read_text()
    papers = parse_atom_feed(xml)
    p = next(p for p in papers if p.arxiv_id == "2508.01234")
    assert p.title == "A Study of Something Interesting"


def test_entry_with_no_authors_raises_and_is_skipped_at_feed_level():
    xml = FIXTURE.read_text()
    papers = parse_atom_feed(xml)
    # the second entry has no <author> elements -> ParsedPaper validation
    # requires non-empty authors, so it should NOT appear in the result
    ids = {p.arxiv_id for p in papers}
    assert "2508.05678" not in ids


def test_malformed_xml_raises_parse_error():
    with pytest.raises(ArxivParseError):
        parse_atom_feed("<not valid xml")


def test_published_date_is_utc_aware():
    xml = FIXTURE.read_text()
    papers = parse_atom_feed(xml)
    p = next(p for p in papers if p.arxiv_id == "2508.01234")
    assert p.published_date is not None
    assert p.published_date.tzinfo is not None
