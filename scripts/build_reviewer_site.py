"""Materialize static route entry points for the GitHub Pages reviewer build.

The generated route folders are committed so direct URLs such as /graphone/
and /validation/ work on any static host. The shared JavaScript fetches only
relative committed-artifact paths under data/.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "reviewer_site"
TEMPLATE = SITE / "template.html"
ROUTES = ("home", "ai-orbit", "graphone", "entities", "relationships", "validation", "mapping", "feasibility", "categories")


def main() -> int:
    template = TEMPLATE.read_text(encoding="utf-8")
    for route in ROUTES:
        base = "./" if route == "home" else "../"
        target = SITE / ("index.html" if route == "home" else f"{route}/index.html")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            template.replace("__BASE_HREF__", base).replace("__ROUTE__", route),
            encoding="utf-8",
        )
    # A static-host fallback still loads the home review interface instead of
    # exposing a generic host error for a malformed reviewer path.
    (SITE / "404.html").write_text(
        template.replace("__BASE_HREF__", "./").replace("__ROUTE__", "home"),
        encoding="utf-8",
    )
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
