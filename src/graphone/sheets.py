"""Optional Google Sheets synchronization for validated GraphOne exports.

The JSON/CSV artifacts under ``data/graphone`` are the source of truth.  This
module only uploads those artifacts after their validation report says passed;
it never calls discovery sources and it never treats a Sheet as an input.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TAB_FILES: tuple[tuple[str, str], ...] = (
    ("Startups", "Startups.csv"),
    ("Products", "Products.csv"),
    ("Research Papers", "Research Papers.csv"),
    ("Jobs", "Jobs.csv"),
    ("News", "News.csv"),
    ("Entity Mapping Log", "Entity Mapping Log.csv"),
)


class GraphOneSheetsExporter:
    """Idempotently clear-and-rewrite all six required GraphOne tabs."""

    def __init__(self, *, spreadsheet_id: str, service_account_json_path: str | Path, batch_size: int = 500):
        if not spreadsheet_id.strip():
            raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID is required for --sync-sheets")
        credential_path = Path(service_account_json_path)
        if not credential_path.is_file():
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON_PATH must name a readable service-account key file")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        credentials = service_account.Credentials.from_service_account_file(str(credential_path), scopes=SCOPES)
        self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self._spreadsheet_id = spreadsheet_id
        self._batch_size = batch_size

    @staticmethod
    def _read_csv(path: Path) -> list[list[str]]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.reader(handle))

    def _ensure_tabs(self) -> None:
        spreadsheet = self._service.spreadsheets().get(
            spreadsheetId=self._spreadsheet_id,
            fields="sheets.properties.title",
        ).execute()
        existing = {
            sheet.get("properties", {}).get("title")
            for sheet in spreadsheet.get("sheets", [])
            if sheet.get("properties", {}).get("title")
        }
        missing = [title for title, _ in TAB_FILES if title not in existing]
        if missing:
            self._service.spreadsheets().batchUpdate(
                spreadsheetId=self._spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": title}}} for title in missing]},
            ).execute()

    def export_validated_directory(self, graphone_dir: str | Path) -> dict[str, int]:
        """Upload all required tabs from a locally validated artifact directory."""

        root = Path(graphone_dir)
        report_path = root / "validation_report.json"
        try:
            validation_report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read GraphOne validation report at {report_path}") from exc
        if validation_report.get("status") != "passed":
            raise ValueError("refusing Sheets export because GraphOne validation has not passed")

        self._ensure_tabs()
        counts: dict[str, int] = {}
        sheets_api = self._service.spreadsheets()
        for tab_name, filename in TAB_FILES:
            rows = self._read_csv(root / "sheets" / filename)
            if not rows:
                raise ValueError(f"validated tab export has no header row: {filename}")
            sheets_api.values().clear(
                spreadsheetId=self._spreadsheet_id,
                range=f"'{tab_name}'",
                body={},
            ).execute()
            for offset in range(0, len(rows), self._batch_size):
                chunk = rows[offset : offset + self._batch_size]
                sheets_api.values().update(
                    spreadsheetId=self._spreadsheet_id,
                    range=f"'{tab_name}'!A{offset + 1}",
                    valueInputOption="RAW",
                    body={"values": chunk},
                ).execute()
            counts[tab_name] = len(rows) - 1
        return counts
