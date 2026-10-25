"""Source-preserving fallback extractor; Arena may replace with code/evidence.py."""
from __future__ import annotations
import csv,json,re,shlex,sqlite3,subprocess,shutil,collections
from pathlib import Path

EMAIL=re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}",re.I)
USER=re.compile(r"\buser_\d+\b",re.I)
HASH=re.compile(r"\b[a-f0-9]{64}\b",re.I)
TIME=re.compile(r"20\d{2}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z")
ID=re.compile(r"\b(?:account|analytics|support|search|cache|export|tombstone|audit_record|backup|data_flow|email_delivery|telemetry|marketing)_\d+\b")
TYPES={"account":"USER_PROFILE","analytics":"ANALYTICS_PROFILE","support":"SUPPORT_MESSAGE",
       "search":"SEARCH_INDEX_ENTRY","cache":"CACHE_ENTRY","export":"USER_EXPORT",
       "tombstone":"ACCOUNT_TOMBSTONE","audit_record":"SECURITY_AUDIT_LOG",
       "backup":"BACKUP_ARCHIVE","data_flow":"DATA_FLOW",
       "email_delivery":"EMAIL_DELIVERY_LOG","telemetry":"PRODUCT_TELEMETRY",
       "marketing":"MARKETING_PROFILE"}
SYS={"account":"account_service","analytics":"analytics_platform","support":"support_platform",
     "search":"search_service","cache":"cache_service","export":"export_service",
     "tombstone":"account_service","audit_record":"security_service","backup":"backup_service",
     "data_flow":"integration_service","email_delivery":"email_delivery_service",
     "telemetry":"analytics_platform","marketing":"marketing_service"}
def cat_for(rid):
    for prefix,cat in TYPES.items():
        if rid.startswith(prefix+"_"):return cat
    return ""
def sys_for(rid):
    for prefix,sys in SYS.items():
        if rid.startswith(prefix+"_"):return sys
    return ""
def extract_refs(record):
    refs=set()
    keynames={"user_id","customer_reference","subject_reference","subject_ref",
              "owner_email","customer_email","requester_email","email","email_hash",
              "phone","customer_phone","requester_phone","full_name","name","lookup_key",
              "subject_key","match_key","matched_value","correlation_key",
              "subject_selector","user_ref"}
    def visit(x,k=""):
        if isinstance(x,dict):
            for key,v in x.items():visit(v,str(key).lower())
        elif isinstance(x,list):
            for v in x:visit(v,k)
        elif isinstance(x,str):
            if k in keynames and x.strip() and x.lower() not in ("none","null"):
                refs.add(x.strip().lower())
            if k in keynames:
                refs.update(m.group().lower() for m in EMAIL.finditer(x))
                refs.update(m.group().lower() for m in USER.finditer(x))
    visit(record)
    return sorted(refs)
def emit(out,file_id,captured,rid,system=None,category=None,state=None,refs=None,fields=None,timestamp=None):
    if not rid or not ID.fullmatch(str(rid)):return
    f=fields if isinstance(fields,dict) else {}
    extra=extract_refs(f)
    if refs:extra+=list(refs)
    out.append({"evidence_id":file_id,"timestamp":timestamp or captured,
                "system_id":system or sys_for(str(rid)),
                "resource_id":str(rid),"category":category or cat_for(str(rid)),
                "state":state or "", "fields":f,"refs":sorted(set(str(v).strip().lower() for v in extra if v)),
                "confidence":2 if state in ("PRESENT","FOUND","ACTIVE","IDENTIFIABLE") else 1})
def parse_json(out,text,file_id,captured):
    obj=json.loads(text)
    def walk(x,system=None,category=None,timestamp=None):
        if isinstance(x,dict):
            system=x.get("system") or x.get("data_store") or x.get("origin_system") or system
            category=x.get("record_type") or x.get("data_category") or category
            timestamp=x.get("observed_at") or x.get("recorded_at") or x.get("captured_at") or x.get("updated_at") or timestamp
            rid=x.get("resource_id")
            if rid:
                record=dict(x)
                if isinstance(x.get("record_json"),str):
                    try:record.update(json.loads(x["record_json"]))
                    except ValueError:pass
                profile=x.get("profile")
                if isinstance(profile,dict):record.update(profile)
                state=x.get("result") or x.get("state") or x.get("status")
                if x.get("status_code")==404:state="ABSENT"
                elif x.get("status_code")==200:state="PRESENT"
                if isinstance(x.get("hits"),dict):
                    state="PRESENT" if x["hits"].get("total",0)>0 else "ABSENT"
                emit(out,file_id,captured,rid,system,category,state,fields=record,timestamp=timestamp or captured)
            if "records" in x and isinstance(x["records"],list):
                for v in x["records"]:walk(v,system,category,timestamp)
                for k,v in x.items():
                    if k!="records" and isinstance(v,(dict,list)):walk(v,system,category,timestamp)
            else:
                for k,v in x.items():
                    if isinstance(v,(dict,list)):
                        nextsys=system
                        if k.endswith("_service") or k in ("analytics_platform","support_platform"):
                            nextsys=k
                        walk(v,nextsys,category,timestamp)
        elif isinstance(x,list):
            for v in x:walk(v,system,category,timestamp)
    walk(obj,timestamp=obj.get("exported_at") if isinstance(obj,dict) else captured)
def parse_sql(out,text,file_id,captured):
    db=sqlite3.connect(":memory:")
    try:
        db.executescript(text)
        tables=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for tbl in tables:
            try:
                db.row_factory=sqlite3.Row
                rows=db.execute('SELECT * FROM "'+tbl.replace('"','""')+'"').fetchall()
            except sqlite3.Error:continue
            for row in rows:
                rec=dict(row)
                if "record_json" in rec:
                    try:rec.update(json.loads(rec["record_json"]))
                    except (ValueError,TypeError):pass
                rid=rec.get("resource_id")
                if not rid:continue
                state=rec.get("result") or rec.get("state") or rec.get("status")
                category=rec.get("record_type") or rec.get("data_category") or cat_for(rid)
                # A stored row is present unless treatment-specific fields establish compliance.
                if state is None:state="PRESENT"
                emit(out,file_id,captured,rid,
                    rec.get("origin_system") or sys_for(rid),category,state,
                    fields=rec,timestamp=captured)
    except sqlite3.Error:
        pass
    finally:db.close()
def tokenize_log(line):
    try:
        return dict(part.split("=",1) for part in shlex.split(line) if "=" in part)
    except ValueError:
        return dict(re.findall(r'(\w+)=("[^"]*"|\S+)',line))
def parse_lines(out,text,file_id,captured):
    traces={};tracecategories={}
    for line in text.splitlines():
        m=TIME.search(line)
        if not m:continue
        ts=m.group()
        if "|" in line:
            bits=[x.strip() for x in line.split("|")]
            if len(bits)>=6 and ID.fullmatch(bits[2]):
                emit(out,file_id,captured,bits[2],bits[1],bits[3],bits[4],refs=[bits[5]],timestamp=ts)
                continue
        kv=tokenize_log(line)
        trace=kv.get("trace_id")
        refs=[kv[k] for k in ("lookup_key","match_key","subject_key","customer_reference","customer_email",
              "email","subject_ref","matched_value","correlation_key","subject_reference","scan_key")
              if kv.get(k) and kv[k].lower()!="null"]
        if trace:
            traces.setdefault(trace,set()).update(x.lower() for x in refs)
            if kv.get("source")=="legacy_contact_index":tracecategories[trace]="SECONDARY_IDENTIFIER"
        rid=kv.get("resource_id")
        if not rid:continue
        ev=kv.get("event","").lower()
        override=tracecategories.get(trace)
        if ev=="contact_lookup_completed":override="SECONDARY_IDENTIFIER"
        if ev=="attachment_pii_scan":override="SUPPORT_ATTACHMENT"
        state=kv.get("result","")
        if ev.endswith("_started") or ev in ("retry","connection_acquired","dependency_retry"):
            continue
        if ev=="profile_lookup_completed":
            state="ABSENT" if kv.get("rows")=="0" or kv.get("http_status")=="404" else "PRESENT"
        elif ev=="index_query_completed":
            state="PRESENT" if kv.get("result")=="hit" or kv.get("total_hits","0")!="0" else "ABSENT"
        elif ev in ("audit_record_read_completed",):
            state="PRESENT" if kv.get("rows")=="1" else "ABSENT"
        elif ev in ("message_pii_scan","attachment_pii_scan"):state="PRESENT"
        elif ev=="analytics_profile_read_completed":
            state="ANONYMIZED" if not any(kv.get(k) not in ("",None,"null") for k in ("customer_reference","email","phone","email_hash")) else "PRESENT"
        elif ev=="support_ticket_read_completed":
            state="PRESENT" if any(kv.get(k) not in ("",None,"null") for k in ("requester_email","requester_phone","requester_name")) else "REDACTED"
        elif ev=="connector_config_read_completed":
            state="ACTIVE" if kv.get("enabled")=="true" else "DISABLED"
        elif ev=="restore_policy_read_completed":
            state="ACTIVE" if kv.get("restore_allowed")=="true" else "BLOCKED"
        elif ev=="restore_candidate_evaluated":
            state="ACTIVE" if kv.get("eligible")=="true" and kv.get("deletion_block")!="true" else "BLOCKED"
        elif ev in ("connector_heartbeat","connector_state_read"):
            state="ACTIVE" if kv.get("enabled")=="true" else "DISABLED"
        elif ev=="deletion_marker_check":
            state="PRESENT" if kv.get("marker_found")=="false" else "ABSENT"
        elif not state and "completed" not in ev:continue
        refs+=list(traces.get(trace,())) if trace else []
        emit(out,file_id,captured,rid,kv.get("service"),override,state,refs,kv,ts)
def parse_pdf(out,path,file_id,captured):
    if not shutil.which("pdftotext"):return
    try:
        p=subprocess.run(["pdftotext","-layout",str(path),"-"],capture_output=True,
                         text=True,timeout=12,check=True)
        parse_lines(out,p.stdout,file_id,captured)
    except (OSError,subprocess.SubprocessError):pass
def extract_facts(dataset_dir):
    root=Path(dataset_dir)
    with open(root/"evidence_files.csv",encoding="utf-8-sig",newline="") as f:
        manifest=list(csv.DictReader(f))
    facts=[]
    for row in manifest:
        p=root/row["file_path"];fid=row["file_id"];cap=row["captured_at"]
        if not p.is_file():continue
        typ=p.suffix.lower()
        if typ==".pdf":
            parse_pdf(facts,p,fid,cap)
        elif typ in (".json",".txt",".log",".sql"):
            try:s=p.read_text(encoding="utf-8")
            except (OSError,UnicodeError):continue
            try:
                if typ==".json":parse_json(facts,s,fid,cap)
                elif typ==".sql":parse_sql(facts,s,fid,cap)
                else:parse_lines(facts,s,fid,cap)
            except (ValueError,TypeError,KeyError):continue
    # Propagate previously evidenced subject links across observations of the same resource.
    links=collections.defaultdict(set)
    for f in facts:links[f["resource_id"]].update(f["refs"])
    for f in facts:f["refs"]=sorted(links[f["resource_id"]])
    return facts
