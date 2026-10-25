"""Participant-visible sample evaluator and exact output contract validator."""
from __future__ import annotations
import argparse,csv,json,collections,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from main import OPS,PHASE
KEYS={"step_no","phase","system_id","resource_id","operation","state","evidence_id"}
LABELS={"COMPLETE","INCOMPLETE","NOT_APPLICABLE"}
def load(path):
    with open(path,encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))
def validate(pred,reqs,ids):
    errors=[];want=[r["case_id"] for r in reqs];got=[r["case_id"] for r in pred]
    if len(got)!=len(want):errors.append(f"row_count expected {len(want)} got {len(got)}")
    if got!=sorted(got):errors.append("not sorted")
    if set(got)!=set(want):errors.append(f"missing={sorted(set(want)-set(got))}; extra={sorted(set(got)-set(want))}")
    if len(set(got))!=len(got):errors.append("duplicate case IDs")
    for r in pred:
        case=r["case_id"];status=r["deletion_status"]
        if status not in LABELS:errors.append(case+": invalid status")
        try:steps=json.loads(r["steps_json"])
        except ValueError:errors.append(case+": invalid steps JSON");continue
        if not isinstance(steps,list):errors.append(case+": steps not array");continue
        if status=="NOT_APPLICABLE" and steps:errors.append(case+": nonempty NOT_APPLICABLE")
        prior=(-1,-1,"","")
        for i,s in enumerate(steps,1):
            if not isinstance(s,dict) or set(s)!=KEYS:
                errors.append(case+f": step {i} invalid fields");continue
            op=s["operation"]
            if op not in OPS:errors.append(case+f": invalid operation {op}");continue
            phase,state,rank=OPS[op]
            if s["step_no"]!=i or s["phase"]!=phase or s["state"]!=state:
                errors.append(case+f": step {i} schema mismatch")
            key=(PHASE[phase],rank,s["system_id"],s["resource_id"])
            if key<prior:errors.append(case+f": step {i} sorting")
            prior=key
            evid=s["evidence_id"]
            if phase=="REMEDIATION" or (status=="INCOMPLETE" and phase=="VERIFICATION"):
                if evid!="":errors.append(case+f": step {i} proposed action cites evidence")
            elif not evid or evid not in ids:errors.append(case+f": step {i} missing/invalid evidence")
    return errors
def evaluate(gold,pred):
    gm={r["case_id"]:r for r in gold}
    pm={r["case_id"]:r for r in pred}
    n=0;status=0;sequence=0;total_true=0;total_pred=0;overlap=0;matchedfield=0;fieldtotal=0
    mismatches=[]
    for case,g in gm.items():
        p=pm.get(case)
        if not p:continue
        n+=1;status+=p["deletion_status"]==g["deletion_status"]
        try:gs=json.loads(g["steps_json"]);ps=json.loads(p["steps_json"])
        except ValueError:continue
        total_true+=len(gs);total_pred+=len(ps)
        a=[tuple(v[k] for k in sorted(KEYS-{"step_no"})) for v in gs]
        b=[tuple(v[k] for k in sorted(KEYS-{"step_no"})) for v in ps]
        ca=collections.Counter(a);cb=collections.Counter(b)
        overlap+=sum((ca&cb).values())
        exact=a==b;sequence+=exact
        for j in range(min(len(gs),len(ps))):
            matchedfield+=sum(gs[j].get(k)==ps[j].get(k) for k in KEYS)
        fieldtotal+=max(len(gs),len(ps))*len(KEYS)
        if g["deletion_status"]!=p["deletion_status"] or not exact:
            mismatches.append({"case_id":case,
              "expected_status":g["deletion_status"],"predicted_status":p["deletion_status"],
              "expected_operations":[x["operation"]+":"+x["resource_id"] for x in gs],
              "predicted_operations":[x["operation"]+":"+x["resource_id"] for x in ps]})
    return {
        "cases":n,"status_correct":status,"status_accuracy":round(status/n,6) if n else None,
        "exact_sequence_correct":sequence,"exact_sequence_accuracy":round(sequence/n,6) if n else None,
        "step_true":total_true,"step_pred":total_pred,"step_exact_overlap":overlap,
        "step_precision":round(overlap/total_pred,6) if total_pred else None,
        "step_recall":round(overlap/total_true,6) if total_true else None,
        "index_aligned_field_accuracy":round(matchedfield/fieldtotal,6) if fieldtotal else None,
        "mismatches":mismatches
    }
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--dataset",default="dataset")
    p.add_argument("--pred",default="sample_predictions.csv")
    p.add_argument("--output",default="code/evaluation/evaluation_report.md")
    a=p.parse_args()
    d=Path(a.dataset)
    gold=load(d/"sample_output.csv")
    pred=load(a.pred)
    ids={r["file_id"] for r in load(d/"evidence_files.csv")}
    ids.update(r["activity_id"] for r in load(d/"system_activity.csv"))
    ids.update(r["audit_id"] for r in load(d/"user_audit_log.csv"))
    errors=validate(pred,load(d/"sample_deletion_requests.csv"),ids)
    metrics=evaluate(gold,pred)
    print(json.dumps({k:v for k,v in metrics.items() if k!="mismatches"},indent=2))
    print("contract_errors:",len(errors))
    t=Path(a.output);t.parent.mkdir(parents=True,exist_ok=True)
    s=["# GhostTrace Evaluation Report","",
       "Evaluation against the **32 participant-provided labelled examples**, not the hidden evaluation set.",
       "","## Actual measured metrics",""]
    for k,v in metrics.items():
        if k!="mismatches":s.append(f"- {k}: **{v}**")
    s+=["","Definitions: status accuracy is exact label matching; sequence accuracy requires exactly matching ordered step objects (excluding step_no, which is checked by schema validation). Step precision/recall use multisets of all six other fields, not fuzzy matches. Field accuracy aligns steps by array index and treats unmatched positions as incorrect. No hidden-label accuracy is claimed.",
        "","## Output contract","",f"- Schema/ordering/evidence violations on samples: **{len(errors)}**"]
    s+=["- "+e for e in errors[:60]]
    s+=["","## Observed failures and root causes",""]
    for m in metrics["mismatches"][:32]:
        s.append(f"- {m['case_id']}: status {m['predicted_status']} vs {m['expected_status']}; expected {', '.join(m['expected_operations'])}; observed {', '.join(m['predicted_operations'])}.")
    s+=["","## Three additional adversarial evaluations (design contracts)","",
       "1. False COMPLETE dashboard: reported_status=COMPLETE is ignored when a verified matching present replica record exists. Expected INCOMPLETE with delete finding/remediation/check.",
       "2. Historical alias: old email mapped through user_audit_log must identify the same user and still detect a secondary-store record under that alias.",
       "3. Active restore: a backup with restore_allowed=true must produce REPORT_RESTORE_RISK, BLOCK_RESTORE, VERIFY_RESTORE_BLOCKED even if the primary account is absent.",
       "These are documented adversarial scenarios; no pass claim is made without executing tests.",
       "","## Limitations","",
       "The baseline extractor does not natively read image pixels; PDF text extraction requires pdftotext. A missing source or unresolved identity never proves absence. Model usage is zero in this baseline and is reported separately. Accuracy on the labelled sample may differ from hidden evaluation.",
       "","## Full evaluation set","",
       "Generated prediction row count and schema validity are checked separately. Hidden canonical labels are not accessible, so hidden accuracy is not measured."]
    t.write_text("\n".join(s)+"\n",encoding="utf-8")
    if errors:raise SystemExit(f"{len(errors)} contract errors")
if __name__=="__main__":main()
