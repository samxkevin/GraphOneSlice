"""
Google Sheets exporter. Reads ONLY from validated_records (never a
system of record itself). Writes are batched via spreadsheets.values.update
(clear-and-rewrite of the whole tab), which makes reruns after a partial
failure safe -- idempotent by construction, not by convention.

Uses the official google-api-python-client. Auth via a service-account
JSON file path from config, never inline credentials.
"""
from __future__ import annotations

from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from src.config.settings import Settings
from src.pipeline.logging_config import get_logger

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

RESEARCH_PAPER_COLUMNS = [
    "schemaVersion", "recordType", "source_name", "source_url", "title",
    "authors", "paper_url", "github_url", "github_stars", "published_date",
    "collectedAt", "github_stars_fetched_at", "github_evidence_type",
]


class SheetsExporter:
    def __init__(self, settings: Settings):
        self._settings = settings
        if not settings.google_service_account_json_path:
            raise ValueError("google_service_account_json_path is not configured")
        if not settings.google_sheets_spreadsheet_id:
            raise ValueError("google_sheets_spreadsheet_id is not configured")
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_json_path, scopes=SCOPES
        )
        self._service = build("sheets", "v4", credentials=creds)

    def _rows_from_payloads(self, payloads: list[dict[str, Any]]) -> list[list[Any]]:
        rows = [RESEARCH_PAPER_COLUMNS]
        for p in payloads:
            row = []
            for col in RESEARCH_PAPER_COLUMNS:
                value = p.get(col)
                if isinstance(value, list):
                    value = "; ".join(value)
                row.append("" if value is None else value)
            rows.append(row)
        return rows

    def export_all(self, payloads: list[dict[str, Any]]) -> None:
        """Full idempotent re-export: clear the tab, rewrite everything
        from current validated_records state. Safe to call repeatedly."""
        tab = self._settings.sheets_research_papers_tab
        spreadsheet_id = self._settings.google_sheets_spreadsheet_id
        sheet = self._service.spreadsheets()

        sheet.values().clear(spreadsheetId=spreadsheet_id, range=tab, body={}).execute()

        rows = self._rows_from_payloads(payloads)
        batch_size = self._settings.sheets_batch_size
        for i in range(0, len(rows), batch_size):
            chunk = rows[i : i + batch_size]
            start_row = i + 1  # 1-indexed, header already included at i=0
            range_str = f"{tab}!A{start_row}"
            sheet.values().update(
                spreadsheetId=spreadsheet_id,
                range=range_str,
                valueInputOption="RAW",
                body={"values": chunk},
            ).execute()
            logger.info(
                "sheets batch written",
                extra={"stage": "sheets_export", "status": "OK", "detail": {"rows": len(chunk)}},
            )
