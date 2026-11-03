"""Multi-document upload: type detection, the documents checklist and /audit-stream."""
import copy

import pytest

import doc_classifier
import main
from checklist import build_checklist
from tests.test_api import CLAIM_PDF, CLINICAL_PDF, TOKEN, client, pdf, read_stream  # noqa: F401 (client is a fixture)
from tests.test_rules import CLAIM, CLINICAL

BILL_PDF = pdf(["CITY CARE HOSPITAL - FINAL BILL", "Bill No: CC/IP/2231   Bill Date: 04/03/2026",
                "Room rent  3 days  12,000", "OT charges  25,000", "Net amount payable: 71,000"])
PHARMACY_PDF = pdf(["SHIV MEDICAL STORE - PHARMACY", "Drug Lic No: DL-20B-1123   GSTIN 07ABCDE1234F1Z5",
                    "Tab Pan 40   Batch PX12   Exp 08/27   Qty 10   MRP 120"])
LAB_PDF = pdf(["PATHOLOGY LABORATORY REPORT", "Sample collected: 01/03/2026",
               "Test Name   Result   Units   Biological Ref. Interval", "Haemoglobin  13.2  g/dL  13-17"])


@pytest.mark.parametrize("text,expected", [
    ("HEALTH INSURANCE CLAIM FORM - PART B\nTo be filled in by the hospital", "claim_form"),
    ("CITY CARE HOSPITAL\nDISCHARGE SUMMARY\nFinal Diagnosis: Acute appendicitis", "discharge_summary"),
    ("FINAL BILL\nBill No: 22\nRoom rent 12,000\nNet amount 71,000", "hospital_bill"),
    ("Apollo Pharmacy\nBatch No A1 Exp 08/27 MRP 120", "pharmacy_bill"),
    ("PATHOLOGY LAB REPORT\nTest Name Result Units Reference range", "investigation_report"),
    ("CASHLESS APPROVAL - AUTHORIZATION LETTER\nApproved amount: 60,000", "pre_auth"),
    ("OPERATION NOTES\nProcedure performed: appendicectomy\nIncision: umbilical", "ot_notes"),
    ("hello world, nothing to see here", "other"),
    # garbled OCR of a real claim form still classifies
    ("CLAIMFORM-PARTB\nTOBEFILLEDINBYTHEHOSPITAL\nDECLARATION BY THE HOSPTAL", "claim_form"),
])
def test_classify(text, expected):
    assert doc_classifier.classify(text)[0] == expected


def test_checklist_flags_missing_and_ticked_but_not_uploaded():
    claim = copy.deepcopy(CLAIM)
    claim["section_d_claim_documents_submitted"]["pharmacy_bills"] = True
    files = [{"name": "c.pdf", "type": "discharge_summary"}, {"name": "k.pdf", "type": "claim_form"}]
    items = {i["type"]: i for i in build_checklist(files, CLINICAL, claim)["items"]}
    assert items["claim_form"]["status"] == "uploaded" and items["claim_form"]["files"] == ["k.pdf"]
    assert items["hospital_bill"]["status"] == "missing"
    assert items["ot_notes"]["level"] == "required"  # the sample claim has a procedure
    assert items["pharmacy_bill"]["form_mismatch"] is True
    assert items["implant_invoice"]["status"] == "not_needed"  # no implant recorded
    assert items["id_card"]["status"] == "recommended"


def test_audit_stream_detects_types_and_returns_checklist(client):
    upload = [("files", (n, b, "application/pdf")) for n, b in
              [("bill.pdf", BILL_PDF), ("claim.pdf", CLAIM_PDF), ("pharmacy.pdf", PHARMACY_PDF),
               ("summary.pdf", CLINICAL_PDF), ("lab.pdf", LAB_PDF)]]
    r = client.post("/audit-stream", files=upload, headers={"X-Backend-Token": TOKEN})
    events = read_stream(r)
    assert events[-1]["type"] == "result", events[-1]
    data = events[-1]["data"]
    types = {f["name"]: f["type"] for f in data["files"]}
    assert types == {"bill.pdf": "hospital_bill", "claim.pdf": "claim_form", "pharmacy.pdf": "pharmacy_bill",
                     "summary.pdf": "discharge_summary", "lab.pdf": "investigation_report"}
    used = {f["used_for"]: f["name"] for f in data["files"] if f["used_for"]}
    assert used == {"clinical": "summary.pdf", "claim": "claim.pdf"}
    items = {i["type"]: i for i in data["checklist"]["items"]}
    assert items["hospital_bill"]["status"] == "uploaded" and items["investigation_report"]["status"] == "uploaded"
    # only the claim form and discharge summary are sent to the LLM, never the bills
    assert "SHIV MEDICAL" not in client.seen["sent"] and "Haemoglobin" not in client.seen["sent"]
    read_done = next(e for e in events if e.get("stage") == "read" and e["status"] == "done")
    assert read_done["detail"].startswith("5 files read")


def test_audit_stream_reports_missing_claim_form(client):
    upload = [("files", ("summary.pdf", CLINICAL_PDF, "application/pdf")), ("files", ("bill.pdf", BILL_PDF, "application/pdf"))]
    last = read_stream(client.post("/audit-stream", files=upload, headers={"X-Backend-Token": TOKEN}))[-1]
    assert last["type"] == "error" and last["status"] == 400
    assert "claim form" in last["detail"]["message"]
    assert any("bill.pdf: looks like hospital bill" in r for r in last["detail"]["reasons"])


def test_audit_stream_limits(client):
    too_many = [("files", (f"{i}.pdf", CLINICAL_PDF, "application/pdf")) for i in range(main.MAX_FILES + 1)]
    assert client.post("/audit-stream", files=too_many, headers={"X-Backend-Token": TOKEN}).status_code == 400
    assert client.post("/audit-stream", files=too_many[:2]).status_code == 401
