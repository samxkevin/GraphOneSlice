"""End-to-end tests on self-created non-organizer evidence."""
import csv,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import evaluate,identity_index,request_is_deletion
from evidence_base import extract_facts
def write_csv(path,rows):
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
class EvidenceToDecision(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/"evidence"/"records").mkdir(parents=True)
        self.user={"user_id":"user_777","email":"newaddress@example.test",
                   "name":"Sample User","phone":"12345","email_hash":"abc",
                   "updated_at":"2026-01-01T00:00:00Z"}
        self.audit={"audit_id":"audit_777","user_id":"user_777","field_name":"email",
                    "old_value":"oldaddress@example.test",
                    "new_value":"newaddress@example.test","event_time":"2026-03-01T00:00:00Z"}
        self.req={"case_id":"test_local","email":"oldaddress@example.test",
                  "request_text":"Please delete my entire account","audit_at":"2026-09-15T00:00:00Z",
                  "reported_status":"COMPLETE"}
        self.users,self.idx=identity_index([self.user],[self.audit])
    def tearDown(self):self.tmp.cleanup()
    def setup_facts(self,records,cap="2026-09-12T00:00:00Z"):
        payload={"exported_at":cap,"records":records}
        (self.root/"evidence"/"records"/"snapshot.json").write_text(json.dumps(payload),encoding="utf-8")
        write_csv(self.root/"evidence_files.csv",
          [{"file_id":"evidence_777","file_path":"evidence/records/snapshot.json",
            "origin":"test_fixture","captured_at":cap}])
        return extract_facts(self.root)
    def result(self,facts,req=None):
        row=evaluate(req or self.req,facts,self.users,self.idx,[self.audit],{})
        return row["deletion_status"],json.loads(row["steps_json"])
    def test_nested_json_exposed_search(self):
        facts=self.setup_facts([{
            "resource_id":"search_777","record_type":"SEARCH_INDEX_ENTRY",
            "system":"search_service","result":"FOUND",
            "subject_reference":"oldaddress@example.test"
        }])
        status,steps=self.result(facts)
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual([s["operation"] for s in steps],
          ["REPORT_REMAINING_RECORD","DELETE_RECORD","VERIFY_RECORD_ABSENT"])
        self.assertEqual(steps[0]["evidence_id"],"evidence_777")
        self.assertEqual(steps[-1]["evidence_id"],"")
    def test_json_backup_recreation(self):
        facts=self.setup_facts([{
            "resource_id":"backup_777","record_type":"BACKUP_ARCHIVE",
            "system":"backup_service","restore_allowed":True,
            "subject_reference":"user_777"}])
        status,steps=self.result(facts)
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual([s["operation"] for s in steps],
          ["REPORT_RESTORE_RISK","BLOCK_RESTORE","VERIFY_RESTORE_BLOCKED"])
    def test_ineligible_later_evidence(self):
        facts=self.setup_facts([{"resource_id":"search_777","record_type":"SEARCH_INDEX_ENTRY",
                "result":"FOUND","subject_reference":"user_777"}],
            "2026-09-20T00:00:00Z")
        status,steps=self.result(facts)
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual(steps,[])
    def test_compliant_retention(self):
        facts=self.setup_facts([{"resource_id":"audit_record_777",
             "record_type":"SECURITY_AUDIT_LOG","system":"security_service",
             "result":"FOUND","subject_reference":"user_777"}])
        status,steps=self.result(facts)
        self.assertEqual(status,"COMPLETE")
        self.assertEqual(steps[0]["operation"],"VERIFY_RECORD_PRESENT")
    def test_unrelated_similar_alias(self):
        facts=self.setup_facts([{"resource_id":"account_776",
             "record_type":"USER_PROFILE","result":"FOUND",
             "subject_reference":"newaddress2@example.test"}])
        status,steps=self.result(facts)
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual(steps,[])
    def test_historical_alias_case_insensitive(self):
        facts=self.setup_facts([{"resource_id":"search_771",
             "record_type":"SEARCH_INDEX_ENTRY","result":"FOUND",
             "subject_reference":"OLDADDRESS@EXAMPLE.TEST"}])
        status,steps=self.result(facts)
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual(steps[0]["resource_id"],"search_771")
if __name__=="__main__":unittest.main()
