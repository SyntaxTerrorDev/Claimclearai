import json
import re
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

import icd10

# -------------------------------------------------------------------------
# SECTION 1: HELPER FUNCTIONS (Data Cleaning & Parsing)
# -------------------------------------------------------------------------

HONORIFICS = r"^(mr|mrs|ms|miss|dr|prof|master|shri|smt|kum)\.?\s+"
SURGICAL_QUALIFICATIONS = re.compile(r"\b(m\.?\s?s|m\.?\s?ch|frcs|dnb|d\.?\s?ortho|ms\s*\(|mch|surg)", re.I)
MANDATORY_FILING_DAYS = 15  # cashless dossier window used in rules_config RULE_14


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().lower()
    text = re.sub(HONORIFICS, "", text)          # strip leading honorific
    text = re.sub(r"\s+", " ", text)              # collapse whitespace
    text = re.sub(r"[^\w\s]", "", text)            # strip punctuation (periods, commas)
    return text.strip()


def parse_iso_datetime(date_str: Optional[str], time_str: Optional[str] = "00:00") -> datetime:
    """Converts separate date and time strings into a single comparable Python datetime object.
    Raises ValueError if date_str is missing/None -- callers should catch this."""
    if not date_str or not str(date_str).strip():
        raise ValueError("date_str is missing or empty")

    clean_date = str(date_str).strip()
    if time_str and str(time_str).strip():
        clean_time = str(time_str).strip()
    else:
        clean_time = "00:00"
    return datetime.strptime(f"{clean_date} {clean_time}", "%Y-%m-%d %H:%M")


def sec(d: Dict[str, Any], key: str) -> Dict[str, Any]:
    return d.get(key, {}) or {}


def money(v) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def blank(v) -> bool:
    return v is None or not str(v).strip()


# -------------------------------------------------------------------------
# SECTION 2: RULE RESULTS
# Each check returns a RuleResult: failed (True/False) or not applicable (None),
# a message, and evidence -- values to highlight in the source PDFs.
#   evidence item: {"doc": "clinical" | "claim", "text": "<value as extracted>", "kind": "value" | "label"}
#   "label" evidence points at where a missing field *should* be (e.g. the "ROHINI" label).
# -------------------------------------------------------------------------

class RuleResult:
    def __init__(self, failed: Optional[bool], message: str = "", evidence: Optional[list] = None, extra: Optional[dict] = None):
        self.failed = failed
        self.message = message
        self.evidence = [e for e in (evidence or []) if e and not blank(e.get("text"))]
        self.extra = extra or {}


def ev(doc: str, text, kind: str = "value") -> dict:
    return {"doc": doc, "text": "" if text is None else str(text), "kind": kind}


def label(doc: str, *names: str) -> dict:
    """Where a *missing* field should be: the viewer tries each label name in order
    and marks the first one it finds (forms word the same field differently)."""
    return ev(doc, "|".join(names), "label")


# Label names that checklist items are printed under on common claim forms.
DOC_LABELS = {
    "Discharge summary": ("Discharge Summary", "Discharge"),
    "Itemized hospital bill": ("Itemized", "Hospital main bill", "Final bill", "Bill"),
    "Investigation reports": ("Investigation reports", "Investigation"),
    "OT notes": ("Operation Theatre", "OT notes", "Operation"),
    "Pre-auth request & approval": ("Pre-authorization request", "Pre-authorisation", "Pre-auth"),
    "Pharmacy bills": ("Pharmacy bills", "Pharmacy"),
}


PASS = RuleResult(False)


def na(reason: str) -> RuleResult:
    return RuleResult(None, reason)


def fail(message: str, *evidence, extra: Optional[dict] = None) -> RuleResult:
    return RuleResult(True, message, list(evidence), extra)


# -------------------------------------------------------------------------
# SECTION 3: AUDIT CHECK FUNCTIONS
# -------------------------------------------------------------------------

def check_rule_01_preauth(clinical, claim, ctx) -> RuleResult:
    """RULE_01: Verifies that surgical claims have an approved Pre-Authorization ID."""
    tr = sec(claim, "section_c_ailment_and_treatment")
    procedure_code = tr.get("procedure_icd10_pcs")
    if blank(procedure_code) and blank(tr.get("procedure_description")):
        return na("No surgical procedure billed.")
    if blank(tr.get("pre_auth_id")):
        return fail("Surgical procedure is billed, but the Pre-Authorization Reference ID is missing or empty.",
                    ev("claim", procedure_code or tr.get("procedure_description")), label("claim", "Pre-authorization Number", "Pre-Authorization", "Pre-Auth", "Preauth"))
    return PASS


def check_rule_02_chronology(clinical, claim, ctx) -> RuleResult:
    """RULE_02: Checks if discharge occurs before admission or conflicts with clinical records."""
    cp = sec(claim, "section_b_patient_details")
    cs = sec(clinical, "hospitalization_timeline")
    evidence = [ev("claim", cp.get("date_of_admission")), ev("claim", cp.get("date_of_discharge"))]
    try:
        claim_adm = parse_iso_datetime(cp.get("date_of_admission"), cp.get("time_of_admission"))
        claim_dis = parse_iso_datetime(cp.get("date_of_discharge"), cp.get("time_of_discharge"))

        if claim_dis <= claim_adm:
            return fail(f"The discharge time ({claim_dis:%d %b %Y %H:%M}) is before or the same as the admission time ({claim_adm:%d %b %Y %H:%M}).", *evidence)

        clin_adm = parse_iso_datetime(cs.get("admission_date"), cs.get("admission_time"))
        clin_dis = parse_iso_datetime(cs.get("discharge_date"), cs.get("discharge_time"))

        if claim_adm.date() != clin_adm.date() or claim_dis.date() != clin_dis.date():
            return fail(
                f"The claim form says the stay was {claim_adm:%d %b} to {claim_dis:%d %b %Y}, "
                f"but the discharge summary says {clin_adm:%d %b} to {clin_dis:%d %b %Y}.",
                *evidence, ev("clinical", cs.get("admission_date")), ev("clinical", cs.get("discharge_date")))
    except (KeyError, ValueError, TypeError, AttributeError) as err:
        return fail("The admission or discharge date is missing or unreadable, so the stay dates could not be checked.", *evidence,
                    label("claim", "Date of Admission", "Admission"))
    return PASS


def check_rule_03_diagnosis_match(clinical, claim, ctx) -> RuleResult:
    """RULE_03: Checks if primary ICD-10 code matches between clinical notes and claim form."""
    clinical_icd = icd10.normalize(sec(clinical, "clinical_assessment").get("primary_icd10_code"))
    claim_icd = icd10.normalize(sec(claim, "section_c_ailment_and_treatment").get("primary_diagnosis_icd10"))

    if not claim_icd:
        return fail("The claim form has no diagnosis code (ICD-10).", label("claim", "ICD 10 Codes", "ICD-10", "ICD"))
    if not clinical_icd:
        return fail("The discharge summary has no diagnosis code (ICD-10), so the claim's code cannot be checked against it.",
                    ev("claim", claim_icd), label("clinical", "Final Diagnosis", "Diagnosis"))
    if clinical_icd != claim_icd:
        return fail(f"The claim form uses diagnosis code {claim_icd}, but the discharge summary says {clinical_icd}.",
                    ev("claim", claim_icd), ev("clinical", clinical_icd))
    return PASS


def check_rule_04_min_24hr_stay(clinical, claim, ctx) -> RuleResult:
    """RULE_04: Flags inpatient admissions under 24 hours not marked as Day Care."""
    cp = sec(claim, "section_b_patient_details")
    admission_type = normalize_text(cp.get("type_of_admission"))
    try:
        adm = parse_iso_datetime(cp.get("date_of_admission"), cp.get("time_of_admission"))
        dis = parse_iso_datetime(cp.get("date_of_discharge"), cp.get("time_of_discharge"))
    except Exception:
        return na("Dates unavailable (reported by RULE_02).")
    duration_hours = (dis - adm).total_seconds() / 3600.0
    # Negative duration is RULE_02's finding; don't stack a nonsensical "-X hours" one.
    if duration_hours < 0:
        return na("Inverted dates (reported by RULE_02).")
    if duration_hours < 24.0 and "day" not in admission_type:
        return fail(f"The patient stayed only {duration_hours:.1f} hours (less than 24), but the admission is not marked as Day Care.",
                    ev("claim", cp.get("time_of_admission")), ev("claim", cp.get("time_of_discharge")), ev("claim", cp.get("type_of_admission")))
    return PASS


def check_rule_05_name_mismatch(clinical, claim, ctx) -> RuleResult:
    """RULE_05: Checks if patient name differs across documents."""
    original_clin = sec(clinical, "patient_demographics").get("patient_name")
    original_claim = sec(claim, "section_b_patient_details").get("patient_name")
    if not normalize_text(original_claim):
        return fail("The patient's name is missing on the claim form.", label("claim", "Name of the Patient", "Patient Name", "Name of Patient"))
    if normalize_text(original_clin) != normalize_text(original_claim):
        return fail(f"The discharge summary says '{original_clin}', but the claim form says '{original_claim}'.",
                    ev("clinical", original_clin), ev("claim", original_claim))
    return PASS


def check_rule_06_gender_icd(clinical, claim, ctx) -> RuleResult:
    """RULE_06: ICD-10 code restricted to the other sex (e.g. obstetric code on a male patient)."""
    code = sec(claim, "section_c_ailment_and_treatment").get("primary_diagnosis_icd10") or \
        sec(clinical, "clinical_assessment").get("primary_icd10_code")
    gender = sec(claim, "section_b_patient_details").get("gender") or sec(clinical, "patient_demographics").get("gender")
    if blank(code) or blank(gender):
        return na("Gender or ICD-10 code not available.")
    reason = icd10.sex_conflict(code, gender)
    if reason:
        return fail(reason, ev("claim", code), ev("claim", gender), ev("clinical", gender))
    proc = normalize_text(sec(claim, "section_c_ailment_and_treatment").get("procedure_description"))
    female_proc = re.search(r"hysterect|caesar|cesar|lscs|oophorect|salping|myomect|d and c|dilatation and curettage", proc)
    male_proc = re.search(r"prostat|orchid|vasectom|circumcis|turp", proc)
    g = normalize_text(gender)
    if (g in ("m", "male") and female_proc) or (g in ("f", "female") and male_proc):
        return fail(f"Procedure '{sec(claim, 'section_c_ailment_and_treatment').get('procedure_description')}' is incompatible with recorded gender '{gender}'.",
                    ev("claim", sec(claim, "section_c_ailment_and_treatment").get("procedure_description")), ev("claim", gender))
    return PASS


def check_rule_07_doctor_reg(clinical, claim, ctx) -> RuleResult:
    """RULE_07: Ensures treating doctor registration number is present."""
    if blank(sec(claim, "section_a_hospital_details").get("doctor_registration_no")):
        return fail("The treating doctor's medical council registration number is missing on the claim form.",
                    label("claim", "Registration No", "Registration Number", "Registration", "Reg No"))
    return PASS


def check_rule_08_hospital_id(clinical, claim, ctx) -> RuleResult:
    """RULE_08: Ensures Hospital ROHINI identification number is present."""
    if blank(sec(claim, "section_a_hospital_details").get("hospital_id_rohini")):
        return fail("The hospital's ROHINI ID is empty in Section A of the claim form.", label("claim", "ROHINI", "Hospital ID"))
    return PASS


def check_rule_09_specialty(clinical, claim, ctx) -> RuleResult:
    """RULE_09: Surgical procedure billed under a non-surgical consultant with no operating surgeon recorded."""
    tr = sec(claim, "section_c_ailment_and_treatment")
    proc = sec(clinical, "procedure_details")
    if blank(tr.get("procedure_description")) and blank(tr.get("procedure_icd10_pcs")) and blank(proc.get("procedure_name")):
        return na("No surgical procedure.")
    hosp = sec(claim, "section_a_hospital_details")
    quals = " ".join(str(x or "") for x in (hosp.get("qualification"),
                                             sec(sec(clinical, "facility"), "treating_doctor").get("qualification")))
    if blank(quals):
        return na("Treating doctor qualification not available.")
    if not SURGICAL_QUALIFICATIONS.search(quals) and blank(proc.get("surgeon_name")):
        return fail(f"A surgical procedure is billed, but the treating doctor's qualification ('{quals.strip()}') is non-surgical "
                    "and no operating surgeon is named in the discharge summary.",
                    ev("claim", hosp.get("qualification")), ev("claim", tr.get("procedure_description")))
    return PASS


def _lines(claim) -> list:
    return [l for l in (sec(claim, "section_e_financial_summary").get("itemized_bill_lines") or []) if isinstance(l, dict)]


def check_rule_10_duplicates(clinical, claim, ctx) -> RuleResult:
    """RULE_10: The same bill line (description + date + amount) appears more than once."""
    lines = _lines(claim)
    if not lines:
        return na("No itemized bill lines in the claim.")
    seen, dups = {}, []
    for l in lines:
        key = (normalize_text(l.get("description")), str(l.get("date") or ""), round(money(l.get("amount")), 2))
        if key[0] and key in seen:
            dups.append(l)
        seen[key] = True
    if dups:
        names = ", ".join(f"'{l.get('description')}' (₹{money(l.get('amount')):,.0f})" for l in dups[:3])
        return fail(f"{len(dups)} duplicate bill entr{'y' if len(dups) == 1 else 'ies'}: {names}.",
                    *[ev("claim", l.get("description")) for l in dups])
    return PASS


def _stay_days(claim) -> Optional[int]:
    cp = sec(claim, "section_b_patient_details")
    try:
        adm = parse_iso_datetime(cp.get("date_of_admission"))
        dis = parse_iso_datetime(cp.get("date_of_discharge"))
        return max(0, (dis.date() - adm.date()).days)
    except Exception:
        return None


def check_rule_11_room_rent(clinical, claim, ctx) -> RuleResult:
    """RULE_11: Multi-day stay with room rent billed as a single lump sum."""
    fin = sec(claim, "section_e_financial_summary")
    days = _stay_days(claim)
    lines = _lines(claim)
    if money(fin.get("room_nursing_charges")) <= 0 or not days or days < 2 or not lines:
        return na("Not a multi-day stay with itemized room charges.")
    room_lines = [l for l in lines if re.search(r"room|bed|ward|nursing", str(l.get("description") or ""), re.I)]
    if len(room_lines) <= 1:
        return fail(f"Room & nursing charges of ₹{money(fin.get('room_nursing_charges')):,.0f} for a {days}-day stay are billed as a single lump sum.",
                    *[ev("claim", l.get("description")) for l in room_lines], label("claim", "Room", "Ward"))
    return PASS


def check_rule_12_implant(clinical, claim, ctx) -> RuleResult:
    """RULE_12: Implant used, but no implant invoice / sticker attached."""
    implant = sec(clinical, "procedure_details").get("implant_used")
    if not implant:
        return na("No implant recorded.")
    if not sec(claim, "section_d_claim_documents_submitted").get("implant_invoice_or_stickers"):
        return fail("The discharge summary records an implant/stent, but the implant invoice or pouch stickers are not marked as submitted.",
                    label("clinical", "Implant", "Stent"), label("claim", "Implant", "Stickers"))
    return PASS


def check_rule_13_bill_dates(clinical, claim, ctx) -> RuleResult:
    """RULE_13: Itemized expenses dated outside the admission-discharge window."""
    lines = [l for l in _lines(claim) if not blank(l.get("date"))]
    cp = sec(claim, "section_b_patient_details")
    if not lines:
        return na("No dated bill lines.")
    try:
        adm = parse_iso_datetime(cp.get("date_of_admission")).date()
        dis = parse_iso_datetime(cp.get("date_of_discharge")).date()
    except Exception:
        return na("Stay dates unavailable.")
    outside = []
    for l in lines:
        try:
            d = datetime.strptime(str(l["date"]).strip(), "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < adm or d > dis:
            outside.append(l)
    if outside:
        return fail(f"{len(outside)} bill line(s) are dated outside the stay ({adm} to {dis}): " +
                    ", ".join(f"'{l.get('description')}' on {l.get('date')}" for l in outside[:3]) + ".",
                    *[ev("claim", l.get("date")) for l in outside])
    return PASS


def check_rule_14_filing_deadline(clinical, claim, ctx) -> RuleResult:
    """RULE_14: Close to / past the filing window counted from discharge."""
    dis = sec(claim, "section_b_patient_details").get("date_of_discharge") or sec(clinical, "hospitalization_timeline").get("discharge_date")
    try:
        d = datetime.strptime(str(dis).strip(), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return na("Discharge date unavailable.")
    elapsed = (ctx["today"] - d).days
    if elapsed < 0:
        return na("Discharge date is in the future.")
    if elapsed > MANDATORY_FILING_DAYS:
        return fail(f"{elapsed} days have passed since discharge ({d}), beyond the {MANDATORY_FILING_DAYS}-day submission window.", ev("claim", dis))
    if elapsed >= MANDATORY_FILING_DAYS - 3:
        return fail(f"{elapsed} days since discharge ({d}): only {MANDATORY_FILING_DAYS - elapsed} day(s) left in the {MANDATORY_FILING_DAYS}-day window.", ev("claim", dis))
    return PASS


def check_rule_15_mandatory_docs(clinical, claim, ctx) -> RuleResult:
    """RULE_15: Required supporting documents not marked as submitted in Section D."""
    docs = sec(claim, "section_d_claim_documents_submitted")
    if not docs:
        return na("Document checklist not found.")
    tr = sec(claim, "section_c_ailment_and_treatment")
    fin = sec(claim, "section_e_financial_summary")
    required = {"discharge_summary": "Discharge summary", "itemized_hospital_bill": "Itemized hospital bill",
                "investigation_reports": "Investigation reports"}
    if not blank(tr.get("procedure_icd10_pcs")) or not blank(tr.get("procedure_description")):
        required["operation_theatre_notes"] = "OT notes"
    if tr.get("pre_auth_obtained") or not blank(tr.get("pre_auth_id")):
        required["original_pre_auth_request_and_approval"] = "Pre-auth request & approval"
    if money(fin.get("medicines_consumables")) > 0:
        required["pharmacy_bills"] = "Pharmacy bills"
    missing = [label for key, label in required.items() if not docs.get(key)]
    if missing:
        return fail("These documents are not attached: " + ", ".join(missing) + ".", *[label("claim", *DOC_LABELS.get(m, (m,))) for m in missing])
    return PASS


def check_rule_16_arithmetic(clinical, claim, ctx) -> RuleResult:
    """RULE_16: Verifies itemized line items sum up to total_claimed_amount."""
    fin = sec(claim, "section_e_financial_summary")
    claimed_total = money(fin.get("total_claimed_amount"))
    computed_sum = sum(money(fin.get(k)) for k in ("room_nursing_charges", "icu_charges", "ot_charges",
                                                     "surgeon_consultation_fees", "investigation_charges", "medicines_consumables"))
    if abs(computed_sum - claimed_total) > 1.0:
        return fail(f"The charges add up to ₹{computed_sum:,.0f}, but the total claimed is ₹{claimed_total:,.0f} (a difference of ₹{abs(claimed_total - computed_sum):,.0f}).",
                    ev("claim", claimed_total), extra={"computed_total": computed_sum})
    return PASS


def check_rule_17_investigation_only(clinical, claim, ctx) -> RuleResult:
    """RULE_17: Admission that looks diagnostic-only (mostly investigations, no treatment)."""
    fin = sec(claim, "section_e_financial_summary")
    total = money(fin.get("total_claimed_amount"))
    if total <= 0:
        return na("No claimed amount.")
    inv = money(fin.get("investigation_charges"))
    treatment = money(fin.get("medicines_consumables")) + money(fin.get("ot_charges")) + money(fin.get("icu_charges"))
    tr = sec(claim, "section_c_ailment_and_treatment")
    has_proc = not blank(tr.get("procedure_icd10_pcs")) or not blank(tr.get("procedure_description"))
    if not has_proc and inv / total >= 0.5 and treatment / total < 0.15:
        return fail(f"Investigations are {inv / total:.0%} of the claim with little active treatment ({treatment / total:.0%}); "
                    "insurers often reject diagnostic-only admissions.", ev("claim", inv))
    return PASS


def check_rule_18_bank_details(clinical, claim, ctx) -> RuleResult:
    """RULE_18: Ensures insured's bank account number and IFSC code are present for NEFT settlement."""
    bank = sec(claim, "section_f_bank_details")
    missing = [n for n, k in (("account number", "account_number"), ("IFSC code", "ifsc_code")) if blank(bank.get(k))]
    if missing:
        return fail(f"The bank {' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} missing, so the insurer cannot pay the money.",
                    label("claim", "IFSC", "Account No", "Bank"))
    return PASS


def check_rule_19_icd_valid(clinical, claim, ctx) -> RuleResult:
    """RULE_19: Malformed code, no ICD-10 chapter, or implausible for the patient's age."""
    raw = sec(claim, "section_c_ailment_and_treatment").get("primary_diagnosis_icd10")
    if blank(raw):
        return na("No code (reported by RULE_03).")
    code = icd10.normalize(raw)
    if not icd10.is_valid_format(code) or not icd10.chapter(code):
        return fail(f"'{raw}' is not a real ICD-10 diagnosis code.", ev("claim", raw))
    age = sec(claim, "section_b_patient_details").get("age_years") or sec(clinical, "patient_demographics").get("age")
    reason = icd10.age_conflict(code, age)
    if reason:
        return fail(reason, ev("claim", raw), ev("claim", age))
    return PASS


def check_rule_20_icd_description(clinical, claim, ctx) -> RuleResult:
    """RULE_20: Diagnosis text points to a different body system than the code."""
    tr = sec(claim, "section_c_ailment_and_treatment")
    code = tr.get("primary_diagnosis_icd10")
    desc = tr.get("primary_diagnosis_description") or sec(clinical, "clinical_assessment").get("final_diagnosis")
    if blank(code) or blank(desc):
        return na("Code or diagnosis text missing.")
    mm = icd10.description_mismatch(code, desc)
    if mm:
        s = mm["suggestions"][0]
        return fail(f"The written diagnosis is '{desc}', but code {icd10.normalize(code)} is for {mm['code_chapter'].lower()}. "
                    f"The right code is probably {s['code']} ({s['description']}).",
                    ev("claim", code), ev("claim", desc), extra={"suggestions": mm["suggestions"]})
    return PASS


# -------------------------------------------------------------------------
# SECTION 4: THE REGISTRY (Connecting JSON Rule IDs to Functions)
# -------------------------------------------------------------------------

RULE_REGISTRY: List[tuple[str, Callable]] = [
    ("RULE_01_PREAUTH_REQ", check_rule_01_preauth),
    ("RULE_02_DATE_CHRONOLOGY", check_rule_02_chronology),
    ("RULE_03_DIAG_PROC_MATCH", check_rule_03_diagnosis_match),
    ("RULE_04_MIN_24HR_STAY", check_rule_04_min_24hr_stay),
    ("RULE_05_NAME_MISMATCH", check_rule_05_name_mismatch),
    ("RULE_06_GENDER_CLINIC_MISMATCH", check_rule_06_gender_icd),
    ("RULE_07_DOCTOR_REG_MISSING", check_rule_07_doctor_reg),
    ("RULE_08_HOSPITAL_ID_MISSING", check_rule_08_hospital_id),
    ("RULE_09_SPECIALTY_MISMATCH", check_rule_09_specialty),
    ("RULE_10_DUPLICATE_LINE_ITEM", check_rule_10_duplicates),
    ("RULE_11_UNITEMIZED_ROOM_RENT", check_rule_11_room_rent),
    ("RULE_12_IMPLANT_INVOICE_MISSING", check_rule_12_implant),
    ("RULE_13_DATE_DISCREPANCY_BILL", check_rule_13_bill_dates),
    ("RULE_14_FILING_DEADLINE_RISK", check_rule_14_filing_deadline),
    ("RULE_15_MISSING_MANDATORY_DOCS", check_rule_15_mandatory_docs),
    ("RULE_16_ARITHMETIC_TOTAL_MISMATCH", check_rule_16_arithmetic),
    ("RULE_17_INVESTIGATION_ONLY_FLAG", check_rule_17_investigation_only),
    ("RULE_18_BANK_DETAILS_MISSING", check_rule_18_bank_details),
    ("RULE_19_ICD_CODE_INVALID", check_rule_19_icd_valid),
    ("RULE_20_ICD_DESCRIPTION_MISMATCH", check_rule_20_icd_description),
]


# -------------------------------------------------------------------------
# SECTION 5: THE AUDIT PIPELINE ENGINE
# -------------------------------------------------------------------------

def run_claim_audit(
    clinical_data: Dict[str, Any],
    claim_data: Dict[str, Any],
    rules_config: Dict[str, Any],
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Runs all checks, deducts points, and prepares the output payload."""
    ctx = {"today": today or date.today()}
    score = 100
    findings: List[Dict[str, Any]] = []
    checks: List[Dict[str, Any]] = []

    for rule_id, check_function in RULE_REGISTRY:
        meta = rules_config.get(rule_id, {})
        try:
            result = check_function(clinical_data or {}, claim_data or {}, ctx)
        except Exception as err:  # one broken rule must never take down the whole audit
            result = na(f"Rule could not be evaluated: {err}")

        status = "failed" if result.failed else "passed" if result.failed is False else "not_applicable"
        checks.append({"rule_id": rule_id, "title": meta.get("title", rule_id), "status": status,
                       "note": result.message if status == "not_applicable" else ""})

        if result.failed:
            deduction = meta.get("deduction", 0)
            score -= deduction
            finding = {
                "rule_id": rule_id,
                "title": meta.get("title", rule_id),
                "category": meta.get("category", "General"),
                "severity": meta.get("severity", "MINOR"),
                "deduction": deduction,
                "regulatory_source": meta.get("regulatory_source", ""),
                "detected_issue": result.message,
                "suggested_fix": meta.get("suggested_fix", ""),
                "evidence": result.evidence,
            }
            finding.update(result.extra)
            findings.append(finding)

    severity_rank = {"CRITICAL": 0, "MAJOR": 1, "MINOR": 2}
    findings.sort(key=lambda f: (severity_rank.get(f["severity"], 3), -f["deduction"]))
    final_score = max(0, score)

    if final_score >= 85:
        status = "READY_TO_SUBMIT"
    elif final_score >= 60:
        status = "ACTION_REQUIRED"
    else:
        status = "HIGH_REJECTION_RISK"

    return {
        "readiness_score": final_score,
        "status": status,
        "total_violations": len(findings),
        "findings": findings,
        "checks": checks,
        "checks_summary": {s: sum(1 for c in checks if c["status"] == s) for s in ("passed", "failed", "not_applicable")},
    }


# -------------------------------------------------------------------------
# SECTION 6: STANDALONE EXECUTION BLOCK
# -------------------------------------------------------------------------

if __name__ == "__main__":
    with open("rules_config.json", "r", encoding="utf-8") as f:
        rules_db = json.load(f)

    with open("discharge_summary.json", "r", encoding="utf-8") as f:
        clinical_mock = json.load(f)

    with open("claim_part_b.json", "r", encoding="utf-8") as f:
        claim_mock = json.load(f)

    audit_report = run_claim_audit(clinical_mock, claim_mock, rules_db)

    print("\n" + "=" * 60)
    print(f" CLAIM AUDIT REPORT | Score: {audit_report['readiness_score']}/100 [{audit_report['status']}]")
    print(f" Total Violations Found: {audit_report['total_violations']}")
    print("=" * 60 + "\n")

    for idx, item in enumerate(audit_report["findings"], 1):
        print(f"[{idx}] {item['title']} (-{item['deduction']} pts)")
        print(f"    Severity : {item['severity']} | Category: {item['category']}")
        print(f"    Issue    : {item['detected_issue']}")
        print(f"    Fix      : {item['suggested_fix']}\n")
