"""Build the separate GraphOne trial artifacts and optionally sync validated CSVs.

Examples:
    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run_graphone.py
    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run_graphone.py --sync-sheets

The second command requires the non-committed Google service-account settings
listed in .env.example. It refuses to upload unless data/graphone validation
has passed and never re-ingests sources while synchronizing Sheets.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from src.graphone.build import DEFAULT_OUTPUT_DIR, build_graphone_outputs
from src.graphone.sheets import GraphOneSheetsExporter


def main() -> int:
    parser = argparse.ArgumentParser(description="Build GraphOne outputs and optionally synchronize Google Sheets.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sync-sheets", action="store_true", help="Upload only the locally validated six-tab CSV exports.")
    parser.add_argument("--skip-build", action="store_true", help="Use existing validated output; meaningful only with --sync-sheets.")
    args = parser.parse_args()

    if args.skip_build and not args.sync_sheets:
        parser.error("--skip-build requires --sync-sheets")

    report: dict[str, object]
    if args.skip_build:
        report = json.loads((args.output_dir / "validation_report.json").read_text(encoding="utf-8"))
        if report.get("status") != "passed":
            raise SystemExit("Refusing Sheets sync: existing GraphOne validation_report.json is not passed.")
    else:
        report = build_graphone_outputs(args.output_dir)

    print("GraphOne validation:", report["status"])
    print("GraphOne counts:", json.dumps(report["summary"], sort_keys=True))

    if args.sync_sheets:
        spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        credential_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "")
        try:
            exporter = GraphOneSheetsExporter(
                spreadsheet_id=spreadsheet_id,
                service_account_json_path=credential_path,
                batch_size=int(os.environ.get("SHEETS_BATCH_SIZE", "500")),
            )
            counts = exporter.export_validated_directory(args.output_dir)
        except (OSError, ValueError) as exc:
            print(f"Google Sheets synchronization not performed: {exc}", file=sys.stderr)
            return 2
        print("Google Sheets rows synchronized:", json.dumps(counts, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
