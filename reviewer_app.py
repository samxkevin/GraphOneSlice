"""Local reviewer for committed GraphOneSlice artifacts only.

This server deliberately imports no ingestion adapters and performs no network
requests. Its API endpoints read the JSON/CSV artifacts committed under data/
and the static UI mirrors those exact files. For an enduring public build, the
GitHub Pages workflow copies ``reviewer_site/`` plus the same data directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parent
SITE_ROOT = PROJECT_ROOT / "reviewer_site"
DATA_ROOT = PROJECT_ROOT / "data"
REVIEWER_ROUTES = {
    "/",
    "/ai-orbit",
    "/graphone",
    "/entities",
    "/relationships",
    "/validation",
    "/mapping",
    "/feasibility",
    "/categories",
}
API_PAYLOADS = {
    "/api/entities": DATA_ROOT / "entities.json",
    "/api/relationships": DATA_ROOT / "relationships.json",
    "/api/validation": DATA_ROOT / "validation_report.json",
    "/api/mapping": DATA_ROOT / "entity_mapping_log.json",
    "/api/feasibility": DATA_ROOT / "source_feasibility.json",
    "/api/graphone": DATA_ROOT / "graphone" / "validation_report.json",
}


class ArtifactReadError(RuntimeError):
    """A committed reviewer artifact is unavailable or malformed."""


@dataclass(frozen=True)
class ArtifactStore:
    """Strict, read-only facade over the committed output files."""

    root: Path = PROJECT_ROOT

    @property
    def data_root(self) -> Path:
        return self.root / "data"

    def read_json(self, relative_path: str) -> Any:
        path = self.data_root / relative_path
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ArtifactReadError(f"artifact is missing: data/{relative_path}") from exc
        except json.JSONDecodeError as exc:
            raise ArtifactReadError(f"artifact is malformed JSON: data/{relative_path}") from exc

    @staticmethod
    def _records(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("records"), list):
            return [item for item in payload["records"] if isinstance(item, dict)]
        return []

    def summary(self) -> dict[str, Any]:
        entities = self._records(self.read_json("entities.json"))
        relationships = self._records(self.read_json("relationships.json"))
        ai_validation = self.read_json("validation_report.json")
        graphone_validation = self.read_json("graphone/validation_report.json")
        graphone_summary = graphone_validation.get("summary", {}) if isinstance(graphone_validation, dict) else {}
        return {
            "ai_orbit": {
                "entities": len(entities),
                "relationships": len(relationships),
                "validation_status": ai_validation.get("status") if isinstance(ai_validation, dict) else None,
                "entity_types": dict(sorted(Counter(item.get("entity_type", "unknown") for item in entities).items())),
            },
            "graphone": {
                "validation_status": graphone_validation.get("status") if isinstance(graphone_validation, dict) else None,
                "summary": graphone_summary,
            },
            "served_from": "committed local data artifacts",
            "ingestion_performed": False,
        }

    def categories(self) -> dict[str, Any]:
        categories_dir = self.data_root / "categories"
        if not categories_dir.is_dir():
            raise ArtifactReadError("artifact directory is missing: data/categories")
        values: dict[str, Any] = {}
        for path in sorted(categories_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ArtifactReadError(f"artifact is malformed JSON: {path.relative_to(self.root)}") from exc
            values[path.stem] = payload
        return values

    def api_payload(self, path: str) -> Any:
        if path == "/api/summary":
            return self.summary()
        if path == "/api/categories":
            return self.categories()
        target = API_PAYLOADS.get(path)
        if target is None:
            raise KeyError(path)
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ArtifactReadError(f"artifact is missing: {target.relative_to(self.root)}") from exc
        except json.JSONDecodeError as exc:
            raise ArtifactReadError(f"artifact is malformed JSON: {target.relative_to(self.root)}") from exc


class ReviewerHandler(SimpleHTTPRequestHandler):
    """Serve static route pages and read-only artifact API endpoints."""

    store = ArtifactStore()
    server_version = "GraphOneSliceReviewer/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003 - stdlib hook
        # Keep request logs concise while retaining normal server diagnostics.
        super().log_message(format, *args)

    def _send_json(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_artifact_error(self, message: str) -> None:
        self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": message, "ingestion_performed": False})

    @staticmethod
    def _safe_child(root: Path, candidate: Path) -> Path | None:
        resolved_root = root.resolve()
        resolved_candidate = candidate.resolve()
        try:
            resolved_candidate.relative_to(resolved_root)
        except ValueError:
            return None
        return resolved_candidate

    def _serve_file(self, path: Path) -> None:
        safe_path = self._safe_child(PROJECT_ROOT, path)
        if safe_path is None or not safe_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content_type = self.guess_type(str(safe_path))
        try:
            with safe_path.open("rb") as source:
                size = safe_path.stat().st_size
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(size))
                self.end_headers()
                self.copyfile(source, self.wfile)
        except OSError:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Could not read reviewer artifact")

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/healthz":
            try:
                summary = self.store.summary()
            except ArtifactReadError as exc:
                self._send_artifact_error(str(exc))
                return
            self._send_json(HTTPStatus.OK, {"status": "ok", **summary})
            return
        if path.startswith("/api/"):
            try:
                payload = self.store.api_payload(path)
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown reviewer API route")
                return
            except ArtifactReadError as exc:
                self._send_artifact_error(str(exc))
                return
            self._send_json(HTTPStatus.OK, payload)
            return
        if path in REVIEWER_ROUTES:
            route_dir = "" if path == "/" else path.lstrip("/")
            self._serve_file(SITE_ROOT / route_dir / "index.html")
            return
        if path.startswith("/data/"):
            relative = path.removeprefix("/data/")
            self._serve_file(DATA_ROOT / relative)
            return
        # Only the small static site bundle is exposed outside data/.
        static_file = SITE_ROOT / path.lstrip("/")
        if static_file.is_file():
            self._serve_file(static_file)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the committed GraphOneSlice reviewer artifacts.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", default=8080, type=int, help="Bind port (default: 8080)")
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), ReviewerHandler)
    print(f"Reviewer serving committed artifacts at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
