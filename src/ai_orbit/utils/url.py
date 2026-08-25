from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    """Normalize a URL for deterministic identity comparisons.

    This does not invent or repair unavailable URLs. It only canonicalizes
    syntax: scheme/host case, default ports, duplicate slashes, trailing slash,
    fragments, and common tracking query parameters.
    """
    if not url or not url.strip():
        return ""
    raw = url.strip()
    parts = urlsplit(raw)
    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()
    if not netloc and parts.path:
        # Accept host/path inputs only for normalization tests; validation still
        # requires real final URLs to include scheme and host.
        reparsed = urlsplit(f"https://{raw}")
        scheme = reparsed.scheme.lower()
        netloc = reparsed.netloc.lower()
        path = reparsed.path
        query = reparsed.query
    else:
        path = parts.path
        query = parts.query

    if (scheme == "https" and netloc.endswith(":443")) or (scheme == "http" and netloc.endswith(":80")):
        netloc = netloc.rsplit(":", 1)[0]

    # Collapse repeated slashes inside the path while preserving a single root.
    path = re.sub(r"/{2,}", "/", path or "/")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if netloc in {"github.com", "api.github.com"}:
        path = path.lower()
    # Quote spaces and other unsafe characters but keep path separators.
    path = quote(path, safe="/%:@")

    query_items = []
    for key, value in parse_qsl(query, keep_blank_values=True):
        lower_key = key.lower()
        if lower_key in _TRACKING_KEYS or lower_key.startswith(_TRACKING_PREFIXES):
            continue
        query_items.append((key, value))
    query_items.sort()
    normalized_query = urlencode(query_items, doseq=True)

    fragment = ""
    if netloc == "github.com" and "/blob/" in path and re.fullmatch(r"L\d+(?:-L\d+)?", parts.fragment or ""):
        # GitHub line anchors are stable evidence locators. Preserve them so
        # source-backed records extracted from different literal lines do not
        # collapse to the same file URL. Other fragments remain stripped.
        fragment = parts.fragment

    return urlunsplit((scheme, netloc, path, normalized_query, fragment))


def is_valid_http_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and bool(parts.netloc)
