"""Which documents this claim needs vs which ones were actually uploaded.

The "needed" logic mirrors RULE_15 (so the checklist and the score agree), and each item also
says whether the claim form's Section D ticks it as attached. A box ticked on the form for a
document that was not uploaded is called out, since the insurer will look for it.
"""
from doc_classifier import LABELS
from rules_engine import blank, money, sec

# (document type, Section D field on the claim form or None)
ITEMS = [
    ("claim_form", None),
    ("discharge_summary", "discharge_summary"),
    ("hospital_bill", "itemized_hospital_bill"),
    ("investigation_report", "investigation_reports"),
    ("pharmacy_bill", "pharmacy_bills"),
    ("ot_notes", "operation_theatre_notes"),
    ("pre_auth", "original_pre_auth_request_and_approval"),
    ("implant_invoice", "implant_invoice_or_stickers"),
    ("id_card", None),
]


def _needed(doc_type: str, clinical: dict, claim: dict) -> tuple[str, str]:
    """(level, reason): level is "required", "recommended" or "if_applicable"."""
    tr = sec(claim, "section_c_ailment_and_treatment")
    fin = sec(claim, "section_e_financial_summary")
    if doc_type in ("claim_form", "discharge_summary"):
        return "required", "Every claim needs this."
    if doc_type == "hospital_bill":
        return "required", "The insurer pays from the itemised final bill."
    if doc_type == "investigation_report":
        return "required", "Test reports back up the diagnosis."
    if doc_type == "pharmacy_bill":
        meds = money(fin.get("medicines_consumables"))
        if meds > 0:
            return "required", f"₹{meds:,.0f} of medicines and consumables are claimed."
        return "if_applicable", "Needed if any medicines were bought."
    if doc_type == "ot_notes":
        proc = tr.get("procedure_description") or tr.get("procedure_icd10_pcs")
        if not blank(proc):
            return "required", f"The claim includes a procedure ({proc})."
        return "if_applicable", "Needed if a surgery or procedure was done."
    if doc_type == "pre_auth":
        if tr.get("pre_auth_obtained") or not blank(tr.get("pre_auth_id")):
            return "required", "The claim form says pre-authorisation was obtained."
        return "if_applicable", "Needed for cashless or planned admissions."
    if doc_type == "implant_invoice":
        if sec(clinical, "procedure_details").get("implant_used"):
            return "required", "The discharge summary records an implant or stent."
        return "if_applicable", "Needed if an implant or stent was used."
    return "recommended", "Insurers usually ask for the policy/TPA card and an ID proof."


def build_checklist(files: list[dict], clinical: dict, claim: dict) -> dict:
    """files: [{"name": ..., "type": ...}]. Returns {"items": [...], "summary": {...}}."""
    ticked = sec(claim, "section_d_claim_documents_submitted")
    items = []
    for doc_type, form_key in ITEMS:
        level, reason = _needed(doc_type, clinical, claim)
        uploaded = [f["name"] for f in files if f["type"] == doc_type]
        marked = bool(ticked.get(form_key)) if form_key and ticked else None
        if uploaded:
            status = "uploaded"
        elif level == "required":
            status = "missing"
        elif level == "recommended":
            status = "recommended"
        else:
            status = "not_needed"
        items.append({
            "type": doc_type, "label": LABELS[doc_type], "level": level, "reason": reason,
            "status": status, "files": uploaded, "marked_on_form": marked,
            # ticked as attached on the claim form, but nothing like it was uploaded
            "form_mismatch": bool(marked) and not uploaded,
        })
    required = [i for i in items if i["level"] == "required"]
    return {"items": items, "summary": {
        "required": len(required),
        "have": sum(1 for i in required if i["status"] == "uploaded"),
        "missing": sum(1 for i in required if i["status"] == "missing"),
        "form_mismatch": sum(1 for i in items if i["form_mismatch"]),
    }}
