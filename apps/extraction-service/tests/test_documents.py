"""Multi-document upload: type detection, the documents checklist and /audit-stream."""
import copy

import pymupdf
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
def merged_pdf(*pdfs: bytes) -> bytes:
    out = pymupdf.open()
    for b in pdfs:
        src = pymupdf.open(stream=b, filetype="pdf")
        out.insert_pdf(src)
        src.close()
    return out.tobytes()


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


def test_split_ranges_keeps_continuation_pages_together():
    from doc_splitter import split_ranges
    pages = ["DISCHARGE SUMMARY\nFinal Diagnosis: appendicitis", "Advice: rest, follow up in a week",
             "HEALTH INSURANCE CLAIM FORM - PART B", "Declaration by the hospital",
             "FINAL BILL\nBill No 22", "Room rent 12,000 Net amount 71,000"]
    assert split_ranges(pages) == [(0, 1), (2, 3), (4, 5)]
    # a normal two-page discharge summary is not split
    assert split_ranges(pages[:2]) == [(0, 1)]


def test_audit_stream_splits_one_merged_pdf(client):
    merged = merged_pdf(CLINICAL_PDF, CLAIM_PDF, BILL_PDF)
    r = client.post("/audit-stream", files=[("files", ("hospital_file.pdf", merged, "application/pdf"))],
                    headers={"X-Backend-Token": TOKEN})
    events = read_stream(r)
    assert events[-1]["type"] == "result", events[-1]
    data = events[-1]["data"]
    assert [(f["name"], f["type"], f["merged_from"]) for f in data["files"]] == [
        ("hospital_file.pdf (page 1)", "discharge_summary", "hospital_file.pdf"),
        ("hospital_file.pdf (page 2)", "claim_form", "hospital_file.pdf"),
        ("hospital_file.pdf (page 3)", "hospital_bill", "hospital_file.pdf"),
    ]
    # the evidence viewer shows just that part's pages
    assert len(data["documents"]["claim"]["pages"]) == 1
    read_done = next(e for e in events if e.get("stage") == "read" and e["status"] == "done")
    assert "1 merged PDF split into parts" in read_done["detail"]


def test_scanned_pages_inside_a_digital_pdf_are_ocred(monkeypatch):
    seen = []

    def fake_ocr(pdf_bytes, dpi=200, on_page=None):
        seen.append(pymupdf.open(stream=pdf_bytes, filetype="pdf").page_count)
        return ["FINAL BILL scanned"], [[{"t": "FINAL", "x0": 0, "y0": 0, "x1": .1, "y1": .1, "c": 90}]]

    monkeypatch.setattr(main, "ocr_pages", fake_ocr)
    blank = pymupdf.open(); blank.new_page(); blank_bytes = blank.tobytes()
    doc = main.read_document(merged_pdf(CLINICAL_PDF, blank_bytes))
    assert doc["method"] == "mixed" and seen == [1]  # only the blank (scanned) page went to OCR
    assert doc["page_texts"][1] == "FINAL BILL scanned" and "DISCHARGE SUMMARY" in doc["page_texts"][0]


def test_claim_form_guidance_page_is_not_the_claim_form():
    text = "GUIDANCE FOR FILLING CLAIM FORM - PART B (To be filled in by the hospital)\nDATA ELEMENT DESCRIPTION FORMAT\nSECTION A - DETAILS OF HOSPITAL"
    assert doc_classifier.classify(text)[0] == "form_guidance"


def test_every_document_gets_a_viewer_tab(client):
    merged = merged_pdf(CLINICAL_PDF, CLAIM_PDF, BILL_PDF)
    r = client.post("/audit-stream", files=[("files", ("hospital_file.pdf", merged, "application/pdf"))],
                    headers={"X-Backend-Token": TOKEN})
    docs = read_stream(r)[-1]["data"]["documents"]
    assert list(docs) == ["clinical", "claim", "doc2"]
    assert docs["doc2"]["label"] == "Hospital bill" and docs["doc2"]["where"] == "p. 3" and len(docs["doc2"]["pages"]) == 1
