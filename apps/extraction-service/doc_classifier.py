"""Work out what kind of claim document a PDF is from its text, with keyword scores (no LLM call).

Each type has strong phrases (3 points) and weak phrases (1 point). Phrases found near the top
of the document, where the title usually is, count three times. Matching also runs on a
"squashed" copy of the text with spaces and punctuation removed, so OCR output like
"CLAIMFORM-PARTB" still counts as "claim form" + "part b".
"""
import re

TYPES = {
    "claim_form": {
        "label": "Claim form",
        "strong": ["claim form", "part b", "to be filled in by the hospital", "declaration by the hospital",
                   "claim documents submitted", "details of hospital", "total claimed amount"],
        "weak": ["claim", "insurance", "policy no", "tpa", "rohini", "insured", "cashless", "reimbursement"],
    },
    "discharge_summary": {
        "label": "Discharge summary",
        "strong": ["discharge summary", "final diagnosis", "course in hospital", "hospital course",
                   "condition at discharge", "advice on discharge", "chief complaints", "discharge advice"],
        "weak": ["discharge", "diagnosis", "admission", "follow up", "history", "examination", "treatment given"],
    },
    "hospital_bill": {
        "label": "Hospital bill",
        "strong": ["final bill", "hospital bill", "itemized bill", "itemised bill", "bill no", "inpatient bill",
                   "amount payable", "net amount", "gross amount", "room rent"],
        "weak": ["bill", "invoice", "charges", "nursing", "amount", "total", "rate"],
    },
    "pharmacy_bill": {
        "label": "Pharmacy bill",
        "strong": ["pharmacy", "chemist", "medical store", "drug lic", "batch no", "mrp"],
        "weak": ["batch", "exp", "qty", "gstin", "tablet", "tab", "syrup", "inj", "cap"],
    },
    "investigation_report": {
        "label": "Investigation report",
        "strong": ["laboratory", "lab report", "pathology", "radiology", "reference range", "biological ref",
                   "test name", "sample collected", "specimen", "ultrasound", "ct scan", "x ray", "mri"],
        "weak": ["result", "units", "haemoglobin", "hemoglobin", "impression", "findings", "report", "normal"],
    },
    "pre_auth": {
        "label": "Pre-authorisation approval",
        "strong": ["authorization letter", "authorisation letter", "approved amount", "cashless approval",
                   "initial approval", "authorization approved", "authorisation approved", "pre auth approval"],
        "weak": ["pre authorization", "pre authorisation", "approved", "approval", "sanctioned", "tpa"],
    },
    "ot_notes": {
        "label": "OT notes",
        "strong": ["operation notes", "operative notes", "ot notes", "operation theatre notes", "procedure performed",
                   "operative findings", "post operative orders"],
        "weak": ["surgeon", "anaesthesia", "anesthesia", "incision", "anaesthetist", "anesthetist", "sutured"],
    },
    "implant_invoice": {
        "label": "Implant invoice / sticker",
        "strong": ["implant invoice", "stent", "implant sticker", "lot no", "serial no", "catalogue no", "catalog no"],
        "weak": ["implant", "invoice", "manufacturer", "expiry", "size"],
    },
    "id_card": {
        "label": "Policy card / ID proof",
        "strong": ["aadhaar", "health card", "e card", "policy card", "tpa card", "valid till", "pan card",
                   "unique identification"],
        "weak": ["member id", "valid", "date of birth", "dob", "card"],
    },
}

OTHER = "other"
LABELS = {key: spec["label"] for key, spec in TYPES.items()} | {OTHER: "Not recognised"}

HEAD_CHARS = 600   # roughly the title block of the first page
MIN_SCORE = 4      # below this the document is "not recognised"
SQUASH_MIN = 7     # phrases at least this long (without spaces) are also matched on the squashed text


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _has(phrase: str, text: str, squashed: str) -> bool:
    if re.search(rf"\b{re.escape(_normalize(phrase))}\b", text):
        return True
    sq = _squash(phrase)
    return len(sq) >= SQUASH_MIN and sq in squashed


def scores(text: str) -> dict[str, int]:
    """Score for every document type (higher = more likely)."""
    body, head = _normalize(text), _normalize(text[:HEAD_CHARS])
    body_sq, head_sq = _squash(text), _squash(text[:HEAD_CHARS])
    out = {}
    for key, spec in TYPES.items():
        total = 0
        for weight, phrases in ((3, spec["strong"]), (1, spec["weak"])):
            for phrase in phrases:
                if _has(phrase, head, head_sq):
                    total += weight * 3
                elif _has(phrase, body, body_sq):
                    total += weight
        out[key] = total
    return out


def classify(text: str) -> tuple[str, dict[str, int]]:
    """(best type or "other", all scores)."""
    s = scores(text)
    best = max(s, key=s.get)
    return (best if s[best] >= MIN_SCORE else OTHER), s
