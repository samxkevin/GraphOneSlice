import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence import extract_facts


class EvidenceExtractionTests(unittest.TestCase):
    def run_dataset(self, files):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        with (root / "evidence_files.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["file_id", "file_path", "captured_at"])
            writer.writeheader()
            for idx, (filename, content) in enumerate(files.items(), 1):
                (root / filename).write_text(content, encoding="utf-8")
                writer.writerow({"file_id": f"evidence_{idx:02d}", "file_path": filename,
                                 "captured_at": "2026-10-01T00:00:00Z"})
        return tmp, extract_facts(root)

    def test_nested_json_resource_and_alias_refs(self):
        payload = {"exported_at": "2026-09-30T10:00:00Z", "account_service": {
            "profile_lookups": [{"resource_id": "account_101", "user_id": "user_101",
                                  "email": "a@example.test", "status": "ANONYMIZED"}]}}
        td, facts = self.run_dataset({"bundle.json": json.dumps(payload)})
        try:
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0]["state"], "ANONYMIZED")
            self.assertIn("user_101", facts[0]["refs"])
            self.assertIn("a@example.test", facts[0]["refs"])
        finally:
            td.cleanup()

    def test_sql_primary_absence_does_not_erase_failover_presence(self):
        sql = """CREATE TABLE primary_snapshot(resource_id TEXT, state TEXT);
        INSERT INTO primary_snapshot VALUES ('account_42','ABSENT');
        CREATE TABLE failover_replica(resource_id TEXT, state TEXT, user_id TEXT);
        INSERT INTO failover_replica VALUES ('account_42','PRESENT','user_42');"""
        td, facts = self.run_dataset({"replicas.sql": sql})
        try:
            observed = [(f["state"], f["fields"].get("user_id")) for f in facts]
            self.assertIn(("ABSENT", None), observed)
            self.assertIn(("PRESENT", "user_42"), observed)
        finally:
            td.cleanup()

    def test_does_not_join_similar_user_strings(self):
        payload = {"records": [
            {"resource_id": "account_12", "user_id": "user_12", "state": "PRESENT"},
            {"resource_id": "account_120", "user_id": "user_120", "state": "PRESENT"}]}
        td, facts = self.run_dataset({"bundle.json": json.dumps(payload)})
        try:
            by_resource = {f["resource_id"]: f["refs"] for f in facts}
            self.assertEqual(by_resource["account_12"], ["user_12"])
            self.assertEqual(by_resource["account_120"], ["user_120"])
        finally:
            td.cleanup()

    def test_logs_require_explicit_readback_and_do_not_promote_task_success(self):
        content = """2026-09-30T10:00:00Z event=task_completed result=SUCCESS resource_id=account_1
2026-09-30T10:01:00Z event=profile_lookup_completed resource_id=account_2 rows=0 trace_id=t-2 user_id=user_2
2026-09-30T10:02:00Z event=profile_lookup_completed resource_id=account_3 trace_id=t-3 user_id=user_3
"""
        td, facts = self.run_dataset({"events.log": content})
        try:
            self.assertEqual([(f["resource_id"], f["state"]) for f in facts], [("account_2", "ABSENT")])
        finally:
            td.cleanup()

    def test_sql_external_attach_is_rejected(self):
        # An unsafe script must not gain access to an arbitrary host database.
        sql = "ATTACH DATABASE '/etc/passwd' AS outside;"
        td, facts = self.run_dataset({"bad.sql": sql})
        try:
            self.assertEqual(facts, [])
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()
