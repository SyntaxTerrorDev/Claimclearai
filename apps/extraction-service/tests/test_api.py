"""API tests with the LLM stubbed out (no network, no API keys used)."""
import copy
import json

import pymupdf
import pytest
from fastapi.testclient import TestClient

import llm_extract
import main
from tests.test_rules import CLAIM, CLINICAL

TOKEN = "test-token"


def pdf(lines):
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((60, 80 + i * 22), line, fontsize=11)
    return doc.tobytes()


CLINICAL_PDF = pdf(["CITY CARE HOSPITAL - DISCHARGE SUMMARY", "Patient Name : Ramesh Kumar   Age: 45   Sex: Male",
                    "Date of Admission: 01/03/2026 10:30   Discharge: 04/03/2026 12:00",
                    "Final Diagnosis: Acute appendicitis  ICD-10: K35.80"])
CLAIM_PDF = pdf(["CLAIM FORM PART B - insurance claim", "Name of the Patient: Ramesh Kumaar",
                 "Policy No: SH/2026/778812   Contact 98765 43210", "Total claimed amount: 71,000"])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("BACKEND_SECRET_TOKEN", TOKEN)
    seen = {}

    def fake_run(clinical_text, claim_text, shield=None, on_event=None):
        emit = on_event or (lambda kind, info=None: None)
        masked_c, masked_k = (shield.mask(clinical_text), shield.mask(claim_text)) if shield else (clinical_text, claim_text)
        seen["sent"] = masked_c + masked_k
        if shield:
            emit("masked", shield.summary())
        emit("llm_start", {"provider": "Gemini"})
        emit("llm_fallback", {"from": "Gemini", "to": "Groq", "reason": "busy (503)"})
        emit("llm_done", {"provider": "Groq"})
        claim = copy.deepcopy(CLAIM)
        claim["section_b_patient_details"]["patient_name"] = "Ramesh Kumaar"
        return {"discharge_summary": copy.deepcopy(CLINICAL), "claim_part_b": claim}

    monkeypatch.setattr(llm_extract, "run", fake_run)
    c = TestClient(main.app)
    c.seen = seen
    return c


def files():
    return {"clinical_doc": ("c.pdf", CLINICAL_PDF, "application/pdf"), "draft_claim": ("k.pdf", CLAIM_PDF, "application/pdf")}


def test_health_reports_version(client):
    assert client.get("/health").json() == {"status": "ok", "version": main.VERSION}


@pytest.mark.parametrize("path", ["/extract", "/extract-text"])
def test_endpoints_require_token(client, path):
    assert client.post(path, files=files()).status_code == 401
    assert client.post(path, files=files(), headers={"X-Backend-Token": "wrong"}).status_code == 401


def test_extract_full_pipeline(client):
    r = client.post("/extract", files=files(), headers={"X-Backend-Token": TOKEN})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "RULE_05_NAME_MISMATCH" in {f["rule_id"] for f in body["audit"]["findings"]}
    page = body["documents"]["claim"]["pages"][0]
    assert page["image"].startswith("data:image/jpeg;base64,") and any(w["t"] == "Kumaar" for w in page["words"])
    assert body["privacy"]["enabled"] and body["privacy"]["masked_total"] >= 3
    assert "Ramesh" not in client.seen["sent"] and "778812" not in client.seen["sent"]
    assert body["extracted"]["claim_part_b"]["section_b_patient_details"]["patient_name"] == "Ramesh Kumaar"


def read_stream(r):
    return [json.loads(line) for line in r.text.splitlines() if line.strip()]


def test_stream_reports_real_stages_in_order(client):
    r = client.post("/extract-stream", files=files(), headers={"X-Backend-Token": TOKEN})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    events = read_stream(r)
    done = [e["stage"] for e in events if e["type"] == "stage" and e["status"] == "done"]
    assert done == ["read", "mask", "extract", "audit", "previews"]
    notes = [e["detail"] for e in events if e["type"] == "note"]
    assert any("switched to Groq" in n for n in notes)
    assert events[-1]["type"] == "result"
    assert events[-1]["data"]["extraction_debug"]["llm_provider"] == "Groq"
    assert "identifiers replaced" in next(e for e in events if e.get("stage") == "mask" and e["status"] == "done")["detail"]


def test_stream_validation_error_is_an_event(client):
    junk = pdf(["hello world", "nothing relevant here at all, just filler text for the page"])
    r = client.post("/extract-stream", headers={"X-Backend-Token": TOKEN},
                    files={"clinical_doc": ("a.pdf", junk, "application/pdf"), "draft_claim": ("b.pdf", junk, "application/pdf")})
    last = read_stream(r)[-1]
    assert last["type"] == "error" and last["status"] == 400


def test_stream_requires_token(client):
    assert client.post("/extract-stream", files=files()).status_code == 401
