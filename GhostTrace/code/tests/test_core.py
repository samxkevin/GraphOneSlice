"""Synthetic contract tests; no organizer-only data used."""
import sys,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import evaluate,identity_index,request_is_deletion
REQ={"case_id":"test_1","email":"new@example.org","audit_at":"2026-09-01T12:00:00Z",
     "request_text":"Please delete my account","reported_status":"COMPLETE"}
USERS=[{"user_id":"user_101","email":"new@example.org","name":"Test Person",
        "phone":"+10000000000","email_hash":"abcd","updated_at":"2026-01-01T00:00:00Z"}]
AUDITS=[{"user_id":"user_101","field_name":"email","old_value":"old@example.org",
         "new_value":"new@example.org","event_time":"2026-02-01T00:00:00Z"}]
def fact(rid,cat,state,refs,when="2026-08-01T00:00:00Z",evid="evidence_01"):
    prefix=rid.split("_")[0]
    system={"account":"account_service","backup":"backup_service",
            "search":"search_service","audit":"security_service"}.get(prefix,"account_service")
    return {"resource_id":rid,"system_id":system,"category":cat,
            "state":state,"refs":refs,"timestamp":when,"evidence_id":evid}
class CoreTests(unittest.TestCase):
    def setUp(self):
        self.users,self.idx=identity_index(USERS,AUDITS)
    def check(self,req,facts):
        r=evaluate(req,facts,self.users,self.idx,AUDITS,{})
        return r["deletion_status"],json.loads(r["steps_json"])
    def test_non_deletion(self):
        r={**REQ,"request_text":"Only send me an export of my data, do not delete anything"}
        status,steps=self.check(r,[fact("account_101","USER_PROFILE","PRESENT",["user_101"])])
        self.assertEqual((status,steps),("NOT_APPLICABLE",[]))
    def test_false_complete_with_replica(self):
        status,steps=self.check(REQ,[fact("account_101","USER_PROFILE","PRESENT",["user_101"])])
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual([s["operation"] for s in steps],
          ["REPORT_REMAINING_RECORD","DELETE_RECORD","VERIFY_RECORD_ABSENT"])
    def test_historical_email(self):
        req={**REQ,"email":"old@example.org"}
        status,steps=self.check(req,[fact("search_301","SEARCH_INDEX_ENTRY","PRESENT",["old@example.org"])])
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual(steps[0]["resource_id"],"search_301")
    def test_active_backup_restoration(self):
        status,steps=self.check(REQ,[fact("backup_51","BACKUP_ARCHIVE","ACTIVE",["user_101"])])
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual([s["operation"] for s in steps],
         ["REPORT_RESTORE_RISK","BLOCK_RESTORE","VERIFY_RESTORE_BLOCKED"])
    def test_simultaneous_replica_drift(self):
        absent=fact("account_101","USER_PROFILE","ABSENT",["user_101"])
        replica=fact("account_101","USER_PROFILE","PRESENT",["user_101"])
        status,steps=self.check(REQ,[absent,replica])
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual(steps[0]["operation"],"REPORT_REMAINING_RECORD")
    def test_simultaneous_analytics_replica_pii(self):
        anonym=fact("analytics_101","ANALYTICS_PROFILE","ANONYMIZED",["user_101"])
        exposed=fact("analytics_101","ANALYTICS_PROFILE","PRESENT",["user_101"])
        status,steps=self.check(REQ,[anonym,exposed])
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual(steps[0]["operation"],"REPORT_EXPOSED_PII")
    def test_ignore_future_evidence(self):
        status,steps=self.check(REQ,[fact("account_101","USER_PROFILE","ABSENT",["user_101"],"2026-09-05T00:00:00Z")])
        self.assertEqual(status,"INCOMPLETE")
        self.assertEqual(steps,[])
    def test_retention(self):
        status,steps=self.check(REQ,[fact("audit_record_51","SECURITY_AUDIT_LOG","PRESENT",["user_101"])])
        self.assertEqual(status,"COMPLETE")
        self.assertEqual(steps[0]["operation"],"VERIFY_RECORD_PRESENT")
    def test_explicit_non_deletion_cases(self):
        for message in (
            "Please stop the promotional emails. I still need the account and my order history, so I am not asking for deletion.",
            "I can't access my profile and need help resetting the login. Do not close the account.",
            "My surname is misspelled on the account. Can you correct it without removing any of my records?",
            "Please remove me from marketing lists only. I still want receipts and service messages for this account.",
            "Can you tell me what personal information you hold about me? This is an information request, not a request to erase it.",
        ):
            self.assertFalse(request_is_deletion(message),message)
    def test_multilingual(self):
        self.assertTrue(request_is_deletion("Je demande la suppression définitive du compte"))
        self.assertTrue(request_is_deletion("このアカウントの完全な削除を依頼します"))
        self.assertTrue(request_is_deletion("Solicito a exclusão permanente da conta associada a este e-mail."))
        self.assertFalse(request_is_deletion("Por favor, não excluam minha conta. Quero apenas uma cópia dos dados."))
if __name__=="__main__":unittest.main()
