"""GhostTrace: evidence-grounded deletion auditor. Uses only participant dataset."""
from __future__ import annotations
import argparse,csv,json,re,sys,collections
from pathlib import Path
from datetime import datetime,timezone
try:
    from evidence import extract_facts
except ImportError:
    from evidence_base import extract_facts

ROOT=Path(__file__).resolve().parents[1]
CATS={
    "USER_PROFILE":"DELETE","SECONDARY_IDENTIFIER":"DELETE",
    "SEARCH_INDEX_ENTRY":"DELETE","CACHE_ENTRY":"DELETE",
    "SUPPORT_ATTACHMENT":"DELETE","USER_EXPORT":"DELETE",
    "MARKETING_PROFILE":"DELETE","SUPPORT_MESSAGE":"REDACT",
    "EMAIL_DELIVERY_LOG":"REDACT","ACCOUNT_TOMBSTONE":"REDACT",
    "ANALYTICS_PROFILE":"ANONYMIZE","PRODUCT_TELEMETRY":"ANONYMIZE",
    "SECURITY_AUDIT_LOG":"RETAIN","LEGAL_HOLD_RECORD":"RETAIN",
    "BACKUP_ARCHIVE":"BLOCK","DATA_FLOW":"DISABLE"
}
OPS={
    "REPORT_REMAINING_RECORD":("FINDING","PRESENT",0),
    "REPORT_EXPOSED_PII":("FINDING","PRESENT",1),
    "REPORT_ACTIVE_DATA_FLOW":("FINDING","ACTIVE",2),
    "REPORT_RESTORE_RISK":("FINDING","ACTIVE",3),
    "DISABLE_DATA_FLOW":("REMEDIATION","DISABLED",0),
    "BLOCK_RESTORE":("REMEDIATION","BLOCKED",1),
    "DELETE_RECORD":("REMEDIATION","ABSENT",2),
    "REDACT_RECORD":("REMEDIATION","REDACTED",3),
    "ANONYMIZE_RECORD":("REMEDIATION","ANONYMIZED",4),
    "VERIFY_RECORD_ABSENT":("VERIFICATION","ABSENT",0),
    "VERIFY_RECORD_PRESENT":("VERIFICATION","PRESENT",1),
    "VERIFY_RECORD_REDACTED":("VERIFICATION","REDACTED",2),
    "VERIFY_RECORD_ANONYMIZED":("VERIFICATION","ANONYMIZED",3),
    "VERIFY_DATA_FLOW_DISABLED":("VERIFICATION","DISABLED",4),
    "VERIFY_RESTORE_BLOCKED":("VERIFICATION","BLOCKED",5)
}
PHASE={"FINDING":0,"REMEDIATION":1,"VERIFICATION":2}
NEGATIVE=[
    r"\b(do not|don.t|not|no longer|never|stop)\s+(want|need|request|ask)\s+(?:.*\s+)?(delet|eras|remov)",
    r"\b(do not|don't|dont)\s+delete\b",r"\bwithout deleting\b",
    r"\b(only|just)\s+(want|need)\s+(?:a\s+)?(copy|download|export|access|correction|update|marketing)",
    r"\b(opt.?out|unsubscribe|marketing preferences|correct my|update my|access my data|download my data)\b"
]
POSITIVE=[
    r"\b(delet|eras|remov|forget|purge|wipe)\w*",
    r"\b(close|closing|terminate|termination)\s+(?:my|this|the|an?)?\s*(?:customer\s*)?(?:account|profile)",
    r"\b(right to be forgotten|permanent account closure)\b",
    r"(elimin|borr|suprim|suppres|effac|supprim|apagar|excluir|löschen|删除|削除|消去|삭제|удал|حذف|حذف|हटा|मिटा)"
]
def load(path):
    with open(path,encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def dt(s):
    if not s:return datetime.min.replace(tzinfo=timezone.utc)
    try:return datetime.fromisoformat(str(s).replace("Z","+00:00"))
    except (TypeError,ValueError):return datetime.min.replace(tzinfo=timezone.utc)
def request_is_deletion(text):
    t=str(text or "").strip().lower()
    if not t:return False
    if any(re.search(p,t) for p in NEGATIVE):return False
    return any(re.search(p,t) for p in POSITIVE)
def identity_index(users,audits):
    records={u["user_id"]:u for u in users}
    emails=collections.defaultdict(set)
    for u in users:
        if u.get("email"):emails[u["email"].strip().lower()].add(u["user_id"])
    for a in audits:
        if a.get("field_name")=="email":
            for k in ("old_value","new_value"):
                if a.get(k):emails[a[k].strip().lower()].add(a["user_id"])
    return records,emails
def identify(req,users,email_idx,audits):
    email=req["email"].strip().lower()
    ids=set(email_idx.get(email,()))
    if len(ids)!=1:return None,{email}
    uid=next(iter(ids)); u=users[uid]
    refs={uid,email}
    for k in ("email","phone","email_hash","name"):
        if u.get(k):refs.add(str(u[k]).strip().lower())
    for a in audits:
        if a.get("user_id")!=uid or dt(a.get("event_time"))>dt(req["audit_at"]):continue
        for k in ("old_value","new_value"):
            if a.get(k):refs.add(str(a[k]).strip().lower())
    return uid,refs
def norm(x):return str(x or "").strip().lower()
def matches(f,refs):
    values=f.get("refs",[])
    if isinstance(values,str):values=[values]
    return any(norm(v) in refs for v in values if v is not None and str(v).strip())
def clean_state(s):
    s=norm(s).upper()
    return {"NOT_FOUND":"ABSENT","MISSING":"ABSENT","DELETED":"ABSENT",
            "FOUND":"PRESENT","HIT":"PRESENT","EXISTS":"PRESENT",
            "IDENTIFIABLE":"PRESENT","ENABLED":"ACTIVE",
            "STOPPED":"DISABLED","REDACTED":"REDACTED",
            "ANONYMIZED":"ANONYMIZED","ANONYMISED":"ANONYMIZED",
            "BLOCKED":"BLOCKED","ABSENT":"ABSENT","ACTIVE":"ACTIVE",
            "PRESENT":"PRESENT","DISABLED":"DISABLED"}.get(s,s)
def category(f):
    x=norm(f.get("category")).upper()
    if x:return x
    r=norm(f.get("resource_id"))
    for prefix,c in (
        ("account_","USER_PROFILE"),("search_","SEARCH_INDEX_ENTRY"),
        ("cache_","CACHE_ENTRY"),("analytics_","ANALYTICS_PROFILE"),
        ("support_","SUPPORT_MESSAGE"),("audit_record_","SECURITY_AUDIT_LOG"),
        ("export_","USER_EXPORT"),("backup_","BACKUP_ARCHIVE"),
        ("data_flow_","DATA_FLOW"),("tombstone_","ACCOUNT_TOMBSTONE"),
        ("email_delivery_","EMAIL_DELIVERY_LOG")):
        if r.startswith(prefix):return c
    return ""
def infer_state(f):
    s=clean_state(f.get("state") or f.get("result"))
    fields=f.get("fields",{})
    if not isinstance(fields,dict):fields={}
    cat=category(f)
    if cat=="BACKUP_ARCHIVE" and "restore_allowed" in fields:
        return "ACTIVE" if fields["restore_allowed"] in (True,"true","True",1) else "BLOCKED"
    if cat=="DATA_FLOW" and "enabled" in fields:
        return "ACTIVE" if fields["enabled"] in (True,"true","True",1) else "DISABLED"
    if cat in ("ANALYTICS_PROFILE","PRODUCT_TELEMETRY") and s in ("","PRESENT","ACTIVE"):
        if not any(fields.get(x) not in (None,"","null") for x in ("user_id","email","phone","email_hash","customer_reference")):
            return "ANONYMIZED"
        return "PRESENT"
    if cat in ("SUPPORT_MESSAGE","EMAIL_DELIVERY_LOG","ACCOUNT_TOMBSTONE") and s in ("","PRESENT","ACTIVE"):
        pii=("email","phone","email_hash","name","requester_email","requester_phone","full_name")
        if not any(fields.get(x) not in (None,"","null") for x in pii):
            return "REDACTED"
        return "PRESENT"
    if not s and fields:return "PRESENT"
    return s
def treatment(cat,rules):
    return rules.get(cat,CATS.get(cat,""))
def make(oper,f,evid=None):
    return {"step_no":0,"phase":OPS[oper][0],"system_id":f["system_id"],
            "resource_id":f["resource_id"],"operation":oper,
            "state":OPS[oper][1],"evidence_id":f.get("evidence_id","") if evid is None else evid}
def evaluate(req,all_facts,users,emailidx,audits,rules):
    if not request_is_deletion(req.get("request_text","")):return {"case_id":req["case_id"],"deletion_status":"NOT_APPLICABLE","steps_json":"[]"}
    uid,refs=identify(req,users,emailidx,audits)
    cutoff=dt(req["audit_at"]); relevant={}
    for f in all_facts:
        if not f.get("resource_id") or not f.get("system_id"):continue
        if dt(f.get("timestamp"))>cutoff:continue
        if not matches(f,refs):continue
        key=(f["system_id"],f["resource_id"])
        if key not in relevant or (dt(f.get("timestamp")),f.get("confidence",1))>(dt(relevant[key].get("timestamp")),relevant[key].get("confidence",1)):
            relevant[key]=f
    findings=[]; remedy=[]; checks=[]
    for k in sorted(relevant):
        f=relevant[k]; cat=category(f); action=treatment(cat,rules);state=infer_state(f)
        if not action or not state:continue
        if action=="RETAIN":
            if state in ("PRESENT","ACTIVE","REDACTED","ANONYMIZED"):
                checks.append(make("VERIFY_RECORD_PRESENT",f))
            continue
        good=None;bad=None;fix=None
        if action=="DELETE":
            if state=="ABSENT":good="VERIFY_RECORD_ABSENT"
            elif state in ("PRESENT","ACTIVE","REDACTED","ANONYMIZED"):
                bad="REPORT_REMAINING_RECORD";fix="DELETE_RECORD";good="VERIFY_RECORD_ABSENT"
        elif action=="REDACT":
            if state=="REDACTED":good="VERIFY_RECORD_REDACTED"
            elif state in ("PRESENT","ACTIVE"):
                bad="REPORT_EXPOSED_PII";fix="REDACT_RECORD";good="VERIFY_RECORD_REDACTED"
        elif action=="ANONYMIZE":
            if state=="ANONYMIZED":good="VERIFY_RECORD_ANONYMIZED"
            elif state in ("PRESENT","ACTIVE","REDACTED"):
                bad="REPORT_EXPOSED_PII";fix="ANONYMIZE_RECORD";good="VERIFY_RECORD_ANONYMIZED"
        elif action=="DISABLE":
            if state in ("DISABLED","BLOCKED"):good="VERIFY_DATA_FLOW_DISABLED"
            elif state=="ACTIVE":
                bad="REPORT_ACTIVE_DATA_FLOW";fix="DISABLE_DATA_FLOW";good="VERIFY_DATA_FLOW_DISABLED"
        elif action=="BLOCK":
            if state=="BLOCKED":good="VERIFY_RESTORE_BLOCKED"
            elif state in ("ACTIVE","PRESENT"):
                bad="REPORT_RESTORE_RISK";fix="BLOCK_RESTORE";good="VERIFY_RESTORE_BLOCKED"
        if bad:findings.append(make(bad,f))
        if fix:remedy.append(make(fix,f,""))
        if good:checks.append(make(good,f))
    status="INCOMPLETE" if findings else "COMPLETE"
    if not checks and not findings:status="INCOMPLETE" # evidence insufficient, never silently assume deletion
    steps=findings+remedy+checks
    steps.sort(key=lambda s:(PHASE[s["phase"]],OPS[s["operation"]][2],s["system_id"],s["resource_id"]))
    for i,s in enumerate(steps,1):
        s["step_no"]=i
        if status=="INCOMPLETE" and s["phase"]=="VERIFICATION":s["evidence_id"]=""
    return {"case_id":req["case_id"],"deletion_status":status,
            "steps_json":json.dumps(steps,ensure_ascii=False,separators=(",",":"))}
def main():
    p=argparse.ArgumentParser();p.add_argument("--dataset",default=str(ROOT/"dataset"))
    p.add_argument("--sample",action="store_true")
    p.add_argument("--output");a=p.parse_args()
    d=Path(a.dataset)
    users,idx=identity_index(load(d/"user_identities.csv"),load(d/"user_audit_log.csv"))
    audits=load(d/"user_audit_log.csv")
    rules={}
    for x in load(d/"deletion_rules.csv"):
        cat=x["data_category"];act=x["required_action"]
        if cat not in rules:rules[cat]=act
    reqs=load(d/("sample_deletion_requests.csv" if a.sample else "deletion_requests.csv"))
    facts=extract_facts(d)
    rows=[evaluate(r,facts,users,idx,audits,rules) for r in reqs]
    rows.sort(key=lambda r:r["case_id"])
    target=Path(a.output) if a.output else ROOT/("sample_predictions.csv" if a.sample else "output.csv")
    target.parent.mkdir(parents=True,exist_ok=True)
    with open(target,"w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["case_id","deletion_status","steps_json"])
        w.writeheader();w.writerows(rows)
    print(json.dumps({"rows":len(rows),"facts":len(facts),
       "statuses":dict(collections.Counter(r["deletion_status"] for r in rows)),
       "output":str(target)}))
if __name__=="__main__":main()
