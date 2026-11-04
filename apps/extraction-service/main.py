import json
import os
import queue
import threading
from pathlib import Path

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Security, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

import doc_classifier
import llm_extract
import rules_engine
from checklist import build_checklist
from doc_splitter import page_subset, pages_subset, part_name, split_ranges
from ocr import ocr_pages
from pdf_parser import extract_page_texts, extract_text, extract_words, is_text_sufficient, render_pages
from phi_shield import Shield

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

VERSION = "2.0.0"  # keep in sync with apps/web/package.json and the git tag

app = FastAPI(title="ClaimClear Extraction Service", version=VERSION)

# The web app runs locally (npm run dev / npm start on port 3000).
# To open it from other devices on the hackathon network, add their origins, e.g.
# FRONTEND_ORIGINS="http://192.168.1.20:3000"
origins = ["http://localhost:3000", "http://127.0.0.1:3000"] + [
    o.strip() for o in os.getenv("FRONTEND_ORIGINS", "").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows POST, GET, OPTIONS, etc.
    allow_headers=["*"],  # Allows all headers (including your X-Backend-Token)
)

# --- API KEY SECURITY ---
API_KEY_NAME = "X-Backend-Token"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def get_api_key(api_key_header: str = Security(api_key_header)):
    # Pulls the secret from your hidden ~/extraction.env file
    expected_key = os.environ.get("BACKEND_SECRET_TOKEN")

    # Failsafe if the environment variable is missing on the server
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: Secret token not set."
        )

    if api_key_header == expected_key:
        return api_key_header

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )


# Load rules config once at startup, not on every request
RULES_CONFIG_PATH = Path(__file__).resolve().parent / "rules_config.json"
with open(RULES_CONFIG_PATH, "r", encoding="utf-8") as f:
    RULES_CONFIG = json.load(f)

# PHI shield is on by default; set PHI_SHIELD=off only for local debugging.
PHI_SHIELD_ENABLED = os.getenv("PHI_SHIELD", "on").lower() not in ("off", "0", "false")

# Limits for the multi-document upload (/audit-stream)
MAX_FILES = 10
MAX_FILE_BYTES = 25 * 1024 * 1024  # a merged scan of the whole claim file can be big


class DocumentExtractionResult(BaseModel):
    text: str
    method: str
    char_count: int


class ExtractTextResponse(BaseModel):
    clinical_doc: DocumentExtractionResult
    draft_claim: DocumentExtractionResult


def send_discord_debug_webhook(clinical: dict, claim: dict, audit: dict, privacy: dict | None):
    """Operational ping only. Never includes names, dates, IDs or any document text:
    those are patient health information and must not leave this server."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        return

    embed = {
        "title": "ClaimClear audit processed",
        "color": 0x0E8177,
        "fields": [
            {"name": "Extraction", "value": f"Clinical: {clinical['method']} ({clinical['char_count']} chars)\n"
                                            f"Claim: {claim['method']} ({claim['char_count']} chars)", "inline": False},
            {"name": "Result", "value": f"Score {audit['readiness_score']}/100 · {audit['status']}\n"
                                        f"Failed rules: {', '.join(f['rule_id'][:7] for f in audit['findings']) or 'none'}", "inline": False},
            {"name": "PHI shield", "value": f"{(privacy or {}).get('masked_total', 0)} identifiers masked before LLM", "inline": False},
        ],
    }
    try:
        requests.post(webhook_url, json={"embeds": [embed]}, timeout=5).raise_for_status()
    except Exception as e:
        print(f"Discord webhook failed: {e}")


def read_document(pdf_bytes: bytes, on_ocr_page=None) -> dict:
    """Text (whole and per page) + per-page word boxes. Direct text layer first; OCR if it looks scanned.
    on_ocr_page(done, total) reports OCR progress."""
    text = extract_text(pdf_bytes)
    if is_text_sufficient(text):
        words, page_texts = extract_words(pdf_bytes), extract_page_texts(pdf_bytes)
        # A merged PDF can mix digital pages with scanned ones: OCR just the pages without text.
        scanned = [i for i, page_text in enumerate(page_texts) if not is_text_sufficient(page_text)]
        if scanned:
            ocr_texts, ocr_words = ocr_pages(pages_subset(pdf_bytes, scanned), on_page=on_ocr_page)
            for i, page_text, page_words in zip(scanned, ocr_texts, ocr_words):
                page_texts[i], words[i] = page_text, page_words
        text = "\n".join(page_texts).strip()
    else:
        page_texts, words = ocr_pages(pdf_bytes, on_page=on_ocr_page)
        scanned = list(range(len(page_texts)))
        text = "\n".join(page_texts).strip()
    return {"text": text, "method": method_for(len(page_texts), len(scanned)), "char_count": len(text),
            "words": words, "page_texts": page_texts, "scanned_pages": scanned}


def method_for(pages: int, scanned: int) -> str:
    return "direct" if scanned == 0 else "ocr" if scanned == pages else "mixed"


def where_label(doc: dict) -> str:
    """Short "where is it" for a viewer tab: page numbers inside a merged PDF, else the file name."""
    first_last = doc.get("page_range")
    if first_last:
        first, last = first_last
        return f"p. {first}" if first == last else f"pp. {first}\u2013{last}"
    return doc.get("name", "")


def split_merged(doc: dict) -> list[dict]:
    """One read document, or its parts if it is a merged PDF holding several documents."""
    ranges = split_ranges(doc["page_texts"])
    if len(ranges) < 2:
        return [doc]
    parts = []
    for first, last in ranges:
        page_texts = doc["page_texts"][first:last + 1]
        text = "\n".join(page_texts).strip()
        scanned = [i - first for i in doc["scanned_pages"] if first <= i <= last]
        parts.append({"text": text, "method": method_for(len(page_texts), len(scanned)), "char_count": len(text),
                      "page_texts": page_texts, "scanned_pages": scanned,
                      "words": doc["words"][first:last + 1], "bytes": page_subset(doc["bytes"], first, last),
                      "name": part_name(doc["name"], first, last), "merged_from": doc["name"],
                      "page_range": [first + 1, last + 1]})
    return parts


def page_previews(pdf_bytes: bytes, words: list) -> list[dict]:
    previews = render_pages(pdf_bytes)
    return [dict(preview, words=words[i] if i < len(words) else []) for i, preview in enumerate(previews)]


def get_document_text(pdf_bytes: bytes) -> DocumentExtractionResult:
    doc = read_document(pdf_bytes)
    return DocumentExtractionResult(text=doc["text"], method=doc["method"], char_count=doc["char_count"])


def is_valid_clinical_doc(text: str) -> bool:
    """Heuristic check to ensure the document contains clinical keywords."""
    keywords = ["patient", "discharge", "diagnosis", "hospital", "admission"]
    return any(word in text.lower() for word in keywords)


def is_valid_claim_form(text: str) -> bool:
    """Heuristic check to ensure the document contains insurance claim keywords."""
    keywords = ["claim", "insurance", "policy", "billing", "charges"]
    return any(word in text.lower() for word in keywords)


def patient_details_from(discharge_summary: dict, claim_part_b: dict) -> dict:
    pb = claim_part_b.get("section_b_patient_details", {}) or {}
    return {
        "name": pb.get("patient_name") or "Unknown",
        "member_id": pb.get("ip_registration_number") or "Unknown",
        "date_of_service": (discharge_summary.get("hospitalization_timeline", {}) or {}).get("admission_date") or "Unknown",
        "principal_diagnosis": (discharge_summary.get("clinical_assessment", {}) or {}).get("final_diagnosis") or "Unknown",
        "discharge_status": (discharge_summary.get("discharge_status", {}) or {}).get("condition_at_discharge") or "Unknown",
    }


def run_audit(discharge_summary: dict, claim_part_b: dict, uploaded: set | None = None) -> dict:
    try:
        report = rules_engine.run_claim_audit(discharge_summary, claim_part_b, RULES_CONFIG, uploaded=uploaded)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rules audit failed: {e}")
    report["patient_details"] = patient_details_from(discharge_summary, claim_part_b)
    return report


@app.get("/health")
def health():
    return {"status": "ok", "version": VERSION}


@app.post("/extract-text", response_model=ExtractTextResponse)
async def extract_text_endpoint(
    clinical_doc: UploadFile = File(...),
    draft_claim: UploadFile = File(...),
    api_key: str = Depends(get_api_key),
):
    """NOTE: this endpoint ONLY does PDF/OCR text extraction.
    It never calls the LLM and never runs the rules audit.
    Use /extract for the full pipeline."""
    return ExtractTextResponse(
        clinical_doc=get_document_text(await clinical_doc.read()),
        draft_claim=get_document_text(await draft_claim.read()),
    )


METHOD_LABEL = {"direct": "digital PDF", "ocr": "scanned, read with OCR", "mixed": "digital PDF with scanned pages"}


def _with_notes(stage: str, work):
    """Run work(note) in a worker thread and yield each note(text) it reports as a progress note
    for `stage`. Generator; its return value (via `yield from`) is work's result."""
    notes: queue.Queue = queue.Queue()
    outcome: dict = {}

    def run():
        try:
            outcome["result"] = work(notes.put)
        except Exception as e:
            outcome["error"] = e
        finally:
            notes.put(None)

    threading.Thread(target=run, daemon=True).start()
    while (detail := notes.get()) is not None:
        yield {"type": "note", "stage": stage, "detail": detail}
    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"]


def _llm_with_events(clinical_text: str, claim_text: str, shield):
    """Run the LLM call in a worker thread and relay its progress callbacks as pipeline events.
    Generator; its return value (via `yield from`) is (structured result, provider)."""
    events: queue.Queue = queue.Queue()
    outcome: dict = {}

    def work():
        try:
            outcome["result"] = llm_extract.run(clinical_text, claim_text, shield=shield,
                                                on_event=lambda kind, info=None: events.put((kind, info or {})))
        except Exception as e:  # surfaced to the client as a 502
            outcome["error"] = e
        finally:
            events.put(("_end", {}))

    threading.Thread(target=work, daemon=True).start()
    while True:
        kind, info = events.get()
        if kind == "_end":
            break
        if kind == "masked":
            yield {"type": "stage", "stage": "mask", "status": "done",
                   "detail": f"{info.get('masked_total', 0)} identifiers replaced before the AI sees the text"}
            yield {"type": "stage", "stage": "extract", "status": "active"}
        elif kind == "llm_start":
            yield {"type": "note", "stage": "extract", "detail": f"Sending masked text to {info['provider']}"}
        elif kind == "llm_retry":
            yield {"type": "note", "stage": "extract",
                   "detail": f"{info['provider']} {info['reason']}, retrying ({info['attempt']}/{info['of']})"}
        elif kind == "llm_fallback":
            yield {"type": "note", "stage": "extract", "detail": f"{info['from']} {info['reason']}, switched to {info['to']}"}
        elif kind == "llm_done":
            outcome["provider"] = info.get("provider")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["result"], outcome.get("provider")


CORE_TYPES = ("claim_form", "discharge_summary")


def pick_core(docs: list[dict]) -> tuple[dict | None, dict | None]:
    """The claim form and discharge summary the audit runs on. Prefers documents classified as
    that type (highest score first); otherwise falls back to the best-scoring document that was
    not recognised as either, so one misread title does not block the whole audit."""
    def best(doc_type: str, taken: dict | None) -> dict | None:
        pool = [d for d in docs if d is not taken]
        typed = [d for d in pool if d["type"] == doc_type]
        fallback = [d for d in pool if d["type"] not in CORE_TYPES and d["scores"][doc_type] >= 2]
        candidates = typed or fallback
        if not candidates:
            return None
        chosen = max(candidates, key=lambda d: d["scores"][doc_type])
        chosen["type"] = doc_type
        return chosen

    claim = best("claim_form", None)
    clinical = best("discharge_summary", claim)
    return clinical, claim


def _type_summary(docs: list[dict]) -> str:
    counts: dict[str, int] = {}
    for d in docs:
        label = doc_classifier.LABELS[d["type"]].lower()
        counts[label] = counts.get(label, 0) + 1
    return ", ".join(f"{n} {label}s" if n > 1 else label for label, n in counts.items())


def audit_pipeline(clinical_bytes: bytes, claim_bytes: bytes):
    """Two-document audit (the original API): which file is which is given, not detected."""
    yield from documents_pipeline([("clinical_doc.pdf", clinical_bytes), ("draft_claim.pdf", claim_bytes)], roles_given=True)


def documents_pipeline(uploads: list[tuple[str, bytes]], roles_given: bool = False):
    """The full audit as a stream of real progress events:
    stage(read) -> stage(mask) -> stage(extract) -> stage(audit) -> stage(previews) -> result.
    `uploads` is [(file name, PDF bytes)]. With roles_given the first file is the clinical record
    and the second the claim form; otherwise each file's type is detected and the claim form and
    discharge summary are picked out, the rest only count towards the documents checklist.
    Only the claim form and discharge summary text is ever sent to the LLM.
    Errors become {"type": "error", "status": ..., "detail": ...}."""
    yield {"type": "stage", "stage": "read", "status": "active"}
    docs = []
    for n, (name, data) in enumerate(uploads, 1):
        prefix = f"File {n} of {len(uploads)}: " if len(uploads) > 1 else ""
        doc = yield from _with_notes("read", lambda note: read_document(
            data, on_ocr_page=lambda done, total: note(f"{prefix}reading scanned pages, {done} of {total}")))
        doc.update(name=name, bytes=data)
        docs.append(doc)

    if roles_given:
        clinical, claim = docs
        clinical["type"], claim["type"] = "discharge_summary", "claim_form"
        yield {"type": "stage", "stage": "read", "status": "done",
               "detail": f"Clinical record: {METHOD_LABEL[clinical['method']]} · Draft claim: {METHOD_LABEL[claim['method']]}"}
        reasons = []
        if not is_valid_clinical_doc(clinical["text"]):
            reasons.append("File 1 does not appear to be a valid clinical document.")
        if not is_valid_claim_form(claim["text"]):
            reasons.append("File 2 does not appear to be a valid insurance claim form.")
        if reasons:
            yield {"type": "error", "status": 400, "detail": {"message": "Document validation failed.", "reasons": reasons}}
            return
    else:
        scanned = sum(1 for d in docs if d["method"] != "direct")  # counted per uploaded file, before splitting
        merged = 0
        split_docs = []
        for doc in docs:
            parts = split_merged(doc)
            merged += len(parts) > 1
            split_docs.extend(parts)
        docs = split_docs
        for doc in docs:
            doc["type"], doc["scores"] = doc_classifier.classify(doc["text"])
        clinical, claim = pick_core(docs)
        files_read = len(uploads)
        yield {"type": "stage", "stage": "read", "status": "done",
               "detail": f"{files_read} file{'' if files_read == 1 else 's'} read"
                         f"{f' ({scanned} scanned)' if scanned else ''}"
                         f"{f' · {merged} merged PDF split into parts' if merged else ''}"
                         f" · found {_type_summary(docs)}"}
        missing = [doc_classifier.LABELS[t].lower() for t, d in (("claim_form", claim), ("discharge_summary", clinical)) if d is None]
        if missing:
            yield {"type": "error", "status": 400, "detail": {
                "message": f"We couldn't find a {' or a '.join(missing)} in your files.",
                "reasons": [f"{d['name']}: looks like {doc_classifier.LABELS[d['type']].lower()}." for d in docs]}}
            return

    shield = Shield() if PHI_SHIELD_ENABLED else None
    if shield is not None:
        yield {"type": "stage", "stage": "mask", "status": "active"}
    else:
        yield {"type": "stage", "stage": "mask", "status": "done", "detail": "Privacy shield is off (PHI_SHIELD=off)"}
        yield {"type": "stage", "stage": "extract", "status": "active"}
    try:
        structured, provider = yield from _llm_with_events(clinical["text"], claim["text"], shield)
    except Exception as e:
        yield {"type": "error", "status": 502, "detail": f"LLM extraction failed: {e}"}
        return
    yield {"type": "stage", "stage": "extract", "status": "done", "detail": f"Structured by {provider or 'the AI'}"}

    yield {"type": "stage", "stage": "audit", "status": "active"}
    discharge_summary = structured.get("discharge_summary", {})
    claim_part_b = structured.get("claim_part_b", {})
    try:
        # With detected documents, what was really uploaded counts, not just the form's tick boxes.
        uploaded = None if roles_given else {d["type"] for d in docs}
        audit_report = run_audit(discharge_summary, claim_part_b, uploaded)
    except HTTPException as e:
        yield {"type": "error", "status": e.status_code, "detail": e.detail}
        return
    cs = audit_report["checks_summary"]
    total = cs["passed"] + cs["failed"] + cs["not_applicable"]
    yield {"type": "stage", "stage": "audit", "status": "done",
           "detail": f"{total} checks run · {cs['failed']} issue{'' if cs['failed'] == 1 else 's'} found"}

    yield {"type": "stage", "stage": "previews", "status": "active"}
    # One viewer tab per document: the two the audit read first, then everything else as uploaded.
    documents = {}
    for key, doc in [("clinical", clinical), ("claim", claim)] + [(f"doc{i}", d) for i, d in enumerate(docs) if d is not clinical and d is not claim]:
        documents[key] = {"method": doc["method"], "pages": page_previews(doc["bytes"], doc["words"]),
                          "label": doc_classifier.LABELS[doc["type"]], "where": where_label(doc)}
    total_pages = sum(len(d["pages"]) for d in documents.values())
    yield {"type": "stage", "stage": "previews", "status": "done",
           "detail": f"{total_pages} pages ready for evidence highlighting"}

    privacy = {"enabled": shield is not None, **(shield.summary() if shield else {"masked_total": 0, "by_type": {}})}
    send_discord_debug_webhook(clinical, claim, audit_report, privacy)

    files = [{"name": d["name"], "type": d["type"], "label": doc_classifier.LABELS[d["type"]], "method": d["method"],
              "pages": len(d["words"]), "used_for": "clinical" if d is clinical else "claim" if d is claim else None,
              "merged_from": d.get("merged_from"), "page_range": d.get("page_range")}
             for d in docs]

    yield {"type": "result", "data": {
        "version": VERSION,
        "extraction_debug": {
            "clinical_doc_method": clinical["method"],
            "draft_claim_method": claim["method"],
            "llm_provider": provider,
        },
        "audit": audit_report,
        "extracted": {"discharge_summary": discharge_summary, "claim_part_b": claim_part_b},
        "documents": documents,
        "files": files,
        "checklist": build_checklist(files, discharge_summary, claim_part_b),
        "privacy": privacy,
    }}


@app.post("/extract")
async def extract_endpoint(
    clinical_doc: UploadFile = File(...),
    draft_claim: UploadFile = File(...),
    api_key: str = Depends(get_api_key),
):
    """Full pipeline as one JSON response (same work as /extract-stream, without progress)."""
    clinical_bytes, claim_bytes = await clinical_doc.read(), await draft_claim.read()

    def run():
        for event in audit_pipeline(clinical_bytes, claim_bytes):
            if event["type"] == "error":
                raise HTTPException(status_code=event["status"], detail=event["detail"])
            if event["type"] == "result":
                return event["data"]

    return await run_in_threadpool(run)


@app.post("/extract-stream")
async def extract_stream_endpoint(
    clinical_doc: UploadFile = File(...),
    draft_claim: UploadFile = File(...),
    api_key: str = Depends(get_api_key),
):
    """Full pipeline streamed as NDJSON: one JSON event per line; the last line is the result or an error.
    Powers the real progress screen in the web app."""
    clinical_bytes, claim_bytes = await clinical_doc.read(), await draft_claim.read()
    return ndjson_response(audit_pipeline(clinical_bytes, claim_bytes))


@app.post("/audit-stream")
async def audit_stream_endpoint(
    files: list[UploadFile] = File(...),
    api_key: str = Depends(get_api_key),
):
    """Multi-document audit, streamed like /extract-stream. Upload every claim document at once
    (claim form, discharge summary, bills, reports, ...), or one merged PDF holding all of them;
    each file's type is detected, merged PDFs are split into their documents, and the result
    includes a documents checklist."""
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Upload at most {MAX_FILES} files.")
    uploads = []
    for i, f in enumerate(files, 1):
        data = await f.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"{f.filename} is larger than {MAX_FILE_BYTES // (1024 * 1024)}MB.")
        uploads.append((f.filename or f"document-{i}.pdf", data))
    return ndjson_response(documents_pipeline(uploads))


def ndjson_response(events) -> StreamingResponse:
    def lines():
        try:
            for event in events:
                yield json.dumps(event) + "\n"
        except Exception as e:  # never leave the client hanging on an unfinished stream
            yield json.dumps({"type": "error", "status": 500, "detail": f"Audit failed: {e}"}) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache"})
