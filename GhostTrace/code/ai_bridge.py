"""Optional GraphOneSlice-inspired three-provider request-intent adjudication.

Production credentials are environment variables. This adapter is intentionally
opt-in: deterministic evidence and rules remain authoritative. Model decisions
are only accepted when exact text quotations and cross-review are validated.
This module does not infer resource status or authorize deletion itself.
"""
from __future__ import annotations
import json,os,time,urllib.request,urllib.error
from dataclasses import dataclass
from typing import Callable

GEMINI="gemini-3.7-flash"
COHERE="command-a-plus-05-2026"
GROQ="openai/gpt-oss-120b"

class ProviderError(Exception):pass
@dataclass
class Intent:
    decision:bool|None
    quote:str|None
    provider:str
    model:str
    supported:bool=False

SYSTEM=("You are interpreting ONLY a customer's message. Decide whether the "
"person explicitly authorizes their account/personal-data deletion, rather "
"than requesting access, an export, a correction, marketing opt-out, or mere "
"information. Treat a request to audit or confirm an earlier deletion as "
"affirming the deletion request. Output JSON with fields deletion_requested "
"(true/false/null), exact_quote (a non-empty exact substring copied from the "
"message supporting your decision), and uncertain (true/false). Do not assume "
"an ambiguous request authorizes deletion. No external facts or guesses.")

SCHEMA={"type":"object","properties":{
 "deletion_requested":{"type":["boolean","null"]},
 "exact_quote":{"type":["string","null"]},
 "uncertain":{"type":"boolean"}},
 "required":["deletion_requested","exact_quote","uncertain"]}

def _http(url,payload,headers,transport=None):
    if transport is not None:return transport(url,payload,headers)
    body=json.dumps(payload,ensure_ascii=False).encode("utf-8")
    for attempt in range(3):
        req=urllib.request.Request(url,body,headers,method="POST")
        try:
            with urllib.request.urlopen(req,timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as ex:
            if ex.code not in (429,500,502,503,504) or attempt==2:
                raise ProviderError(f"HTTP {ex.code}") from ex
            time.sleep(min(2**attempt,4))
        except (urllib.error.URLError,TimeoutError,OSError) as ex:
            if attempt==2:raise ProviderError("Transport unavailable") from ex
            time.sleep(min(2**attempt,4))
    raise ProviderError("Transport failed")

def _parsed(raw,source,provider,model):
    try:
        obj=json.loads(raw) if isinstance(raw,str) else raw
        q=obj.get("exact_quote")
        value=obj.get("deletion_requested")
        good=(isinstance(q,str) and bool(q.strip()) and q in source
              and isinstance(value,bool) and obj.get("uncertain") is False)
        return Intent(value if good else None,q if good else None,provider,model,good)
    except (ValueError,TypeError,AttributeError):
        return Intent(None,None,provider,model,False)

def gemini(text,transport=None):
    key=os.getenv("GEMINI_API_KEY")
    if not key:raise ProviderError("Missing GEMINI_API_KEY")
    payload={"model":os.getenv("GHOSTTRACE_GEMINI_MODEL",GEMINI),
             "input":SYSTEM+"\nORIGINAL CUSTOMER MESSAGE:\n"+text,
             "response_format":{"type":"text","mime_type":"application/json","schema":SCHEMA}}
    data=_http("https://generativelanguage.googleapis.com/v1beta/interactions",payload,
               {"x-goog-api-key":key,"Content-Type":"application/json"},transport)
    for step in data.get("steps",[]):
        if step.get("type")=="model_output":
            for item in step.get("content",[]):
                if item.get("type")=="text":
                    return _parsed(item.get("text",""),text,"Google Gemini",payload["model"])
    raise ProviderError("Gemini returned no output")

def cohere(text,gemini_draft=None,transport=None):
    key=os.getenv("COHERE_API_KEY")
    if not key:raise ProviderError("Missing COHERE_API_KEY")
    instruction=SYSTEM+"\nOriginal customer message:\n"+text
    if gemini_draft:
        instruction+=("\nReview this prior draft. Do not copy unsupported assertions: "
                      +json.dumps(gemini_draft.__dict__))
    payload={"model":os.getenv("GHOSTTRACE_COHERE_MODEL",COHERE),
             "messages":[{"role":"user","content":instruction}],
             "temperature":0,"response_format":{"type":"json_object","schema":SCHEMA}}
    data=_http("https://api.cohere.com/v2/chat",payload,
              {"Authorization":"Bearer "+key,"Content-Type":"application/json"},transport)
    for part in data.get("message",{}).get("content",[]):
        if isinstance(part,dict) and part.get("type")=="text":
            return _parsed(part.get("text",""),text,"Cohere",payload["model"])
    raise ProviderError("Cohere returned no text")

def groq(text,draft,review,transport=None):
    key=os.getenv("GROQ_API_KEY")
    if not key:raise ProviderError("Missing GROQ_API_KEY")
    payload={"model":os.getenv("GHOSTTRACE_GROQ_MODEL",GROQ),
             "messages":[{"role":"system","content":SYSTEM},
                {"role":"user","content":"ORIGINAL MESSAGE:\n"+text
                 +"\nFirst extraction: "+json.dumps(draft.__dict__)
                 +"\nIndependent review: "+json.dumps(review.__dict__)
                 +"\nAdjudicate only from original source and cite a literal exact quote."}],
             "temperature":0,"response_format":{"type":"json_object"}}
    data=_http("https://api.groq.com/openai/v1/chat/completions",payload,
              {"Authorization":"Bearer "+key,"Content-Type":"application/json"},transport)
    try:
        raw=data["choices"][0]["message"]["content"]
    except (KeyError,IndexError,TypeError) as ex:
        raise ProviderError("Groq returned no completion") from ex
    return _parsed(raw,text,"Groq",payload["model"])

def decide_intent(text,transport=None):
    """Return True/False only with source-validated provider consensus, else None.

    The agent does not call providers unless GHOSTTRACE_AI_INTENT=1 and ALL
    required credentials are present. Does not invent usage/cost totals.
    """
    if os.getenv("GHOSTTRACE_AI_INTENT")!="1":return None
    if not all(os.getenv(v) for v in ("GEMINI_API_KEY","COHERE_API_KEY","GROQ_API_KEY")):
        return None
    try:
        draft=gemini(text,transport)
        review=cohere(text,draft,transport)
        final=groq(text,draft,review,transport)
    except ProviderError:return None
    if not all(x.supported for x in (draft,review,final)):return None
    if draft.decision!=review.decision or review.decision!=final.decision:return None
    return final.decision
