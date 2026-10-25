"""Offline contract tests for optional three-provider evidence review."""
import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ai_bridge import decide_intent,gemini,cohere,groq,GEMINI,COHERE,GROQ
TEXT="I authorize removal of all my account data."
class ModelIntentTests(unittest.TestCase):
    def reply(self,url,payload,headers):
        body='{"deletion_requested":true,"exact_quote":"removal of all my account data","uncertain":false}'
        if "generativelanguage.googleapis.com" in url:
            return {"steps":[{"type":"model_output","content":[{"type":"text","text":body}]}]}
        if "api.cohere.com" in url:
            return {"message":{"content":[{"type":"text","text":body}]}}
        if "api.groq.com" in url:
            return {"choices":[{"message":{"content":body}}]}
        raise AssertionError(url)
    def test_missing_credentials_no_calls(self):
        with patch.dict(os.environ,{"GHOSTTRACE_AI_INTENT":"1","GEMINI_API_KEY":"",
                                    "COHERE_API_KEY":"","GROQ_API_KEY":""}):
            self.assertIsNone(decide_intent(TEXT,lambda *a: self.fail("must not call provider")))
    def test_full_consensus_with_quotes(self):
        with patch.dict(os.environ,{"GHOSTTRACE_AI_INTENT":"1","GEMINI_API_KEY":"test-only",
                                    "COHERE_API_KEY":"test-only","GROQ_API_KEY":"test-only"}):
            self.assertIs(decide_intent(TEXT,self.reply),True)
    def test_quote_must_be_exact(self):
        def bad(url,payload,headers):
            response=self.reply(url,payload,headers)
            if "generativelanguage" in url:
                response["steps"][0]["content"][0]["text"]='{"deletion_requested":true,"exact_quote":"not present here","uncertain":false}'
            return response
        with patch.dict(os.environ,{"GHOSTTRACE_AI_INTENT":"1","GEMINI_API_KEY":"test-only",
                                    "COHERE_API_KEY":"test-only","GROQ_API_KEY":"test-only"}):
            self.assertIsNone(decide_intent(TEXT,bad))
    def test_disagreement_quarantine(self):
        def disagree(url,payload,headers):
            response=self.reply(url,payload,headers)
            if "api.cohere.com" in url:
                response["message"]["content"][0]["text"]='{"deletion_requested":false,"exact_quote":"removal of all my account data","uncertain":false}'
            return response
        with patch.dict(os.environ,{"GHOSTTRACE_AI_INTENT":"1","GEMINI_API_KEY":"test-only",
                                    "COHERE_API_KEY":"test-only","GROQ_API_KEY":"test-only"}):
            self.assertIsNone(decide_intent(TEXT,disagree))
    def test_disabled_model_mode_no_calls(self):
        with patch.dict(os.environ,{"GHOSTTRACE_AI_INTENT":"0"}):
            self.assertIsNone(decide_intent(TEXT,self.reply))
if __name__=="__main__":unittest.main()
