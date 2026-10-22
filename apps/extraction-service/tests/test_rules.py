"""Rules engine tests: a clean claim scores 100, and each defect trips exactly its rule.
Run from apps/extraction-service:  python -m pytest -q
"""
import copy
import json
from datetime import date
from pathlib import Path

import pytest

import rules_engine as re_

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "rules_config.json").read_text(encoding="utf-8"))
TODAY = date(2026, 3, 10)

CLINICAL = {
    "facility": {"hospital_name": "City Care Hospital", "department": "General Surgery",
                 "treating_doctor": {"name": "Dr. Anil Mehta", "qualification": "MS (General Surgery)",
                                     "council_registration_number": "DMC/45821", "council_state": "Delhi"}},
    "patient_demographics": {"patient_name": "Ramesh Kumar", "age": 45, "gender": "Male", "uhid": "CC-917", "ipd_number": "4471"},
    "hospitalization_timeline": {"admission_date": "2026-03-01", "admission_time": "10:30",
                                 "discharge_date": "2026-03-04", "discharge_time": "12:00",
                                 "total_stay_duration_hours": 73.5, "admission_type": "Emergency"},
    "clinical_assessment": {"chief_complaints": "Pain abdomen", "provisional_diagnosis": "Acute appendicitis",
                            "final_diagnosis": "Acute appendicitis", "primary_icd10_code": "K35.80", "secondary_icd10_codes": []},
    "procedure_details": {"procedure_name": "Laparoscopic appendicectomy", "procedure_code": "0DTJ4ZZ",
                          "procedure_date": "2026-03-01", "anesthesia_type": "GA", "surgeon_name": "Dr. Anil Mehta",
                          "histopathology_sent": True, "implant_used": False},
    "discharge_status": {"condition_at_discharge": "Stable", "follow_up_date": "2026-03-11"},
}

CLAIM = {
    "section_a_hospital_details": {"hospital_name": "City Care Hospital", "hospital_id_rohini": "8900080123456",
                                   "hospital_type": "Network", "treating_doctor_name": "Dr. Anil Mehta",
                                   "qualification": "MS (General Surgery)", "doctor_registration_no": "DMC/45821", "phone_number": None},
    "section_b_patient_details": {"patient_name": "Mr. Ramesh Kumar", "ip_registration_number": "4471", "gender": "Male", "age_years": 45,
                                  "date_of_admission": "2026-03-01", "time_of_admission": "10:30",
                                  "date_of_discharge": "2026-03-04", "time_of_discharge": "12:00",
                                  "type_of_admission": "Emergency", "status_at_discharge": "Discharged"},
    "section_c_ailment_and_treatment": {"primary_diagnosis_description": "Acute appendicitis", "primary_diagnosis_icd10": "K35.80",
                                        "procedure_description": "Laparoscopic appendicectomy", "procedure_icd10_pcs": "0DTJ4ZZ",
                                        "pre_auth_obtained": True, "pre_auth_id": "PA-2026-5541", "system_of_medicine": "Allopathy"},
    "section_d_claim_documents_submitted": {"discharge_summary": True, "investigation_reports": True, "operation_theatre_notes": True,
                                            "original_pre_auth_request_and_approval": True, "itemized_hospital_bill": True,
                                            "pharmacy_bills": True, "implant_invoice_or_stickers": False},
    "section_e_financial_summary": {"room_nursing_charges": 12000, "icu_charges": 0, "ot_charges": 25000,
                                    "surgeon_consultation_fees": 18000, "investigation_charges": 6500,
                                    "medicines_consumables": 9500, "total_claimed_amount": 71000,
                                    "itemized_bill_lines": [
                                        {"description": "Room rent - semi private (day 1)", "date": "2026-03-01", "amount": 4000},
                                        {"description": "Room rent - semi private (day 2)", "date": "2026-03-02", "amount": 4000},
                                        {"description": "Room rent - semi private (day 3)", "date": "2026-03-03", "amount": 4000},
                                        {"description": "CBC", "date": "2026-03-01", "amount": 450}]},
    "section_f_bank_details": {"account_holder_name": "Ramesh Kumar", "bank_name": "SBI", "account_number": "123456789012", "ifsc_code": "SBIN0001234"},
}


def audit(clinical=None, claim=None):
    return re_.run_claim_audit(clinical or CLINICAL, claim or CLAIM, CONFIG, today=TODAY)


def failed_ids(report):
    return {f["rule_id"] for f in report["findings"]}


def test_clean_claim_scores_100():
    r = audit()
    assert failed_ids(r) == set(), r["findings"]
    assert r["readiness_score"] == 100 and r["status"] == "READY_TO_SUBMIT"
    assert len(r["checks"]) == 20
    assert r["checks_summary"]["failed"] == 0


def mutate(path, value, base=None):
    data = copy.deepcopy(base or CLAIM)
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return data


@pytest.mark.parametrize("path,value,rule", [
    (("section_c_ailment_and_treatment", "pre_auth_id"), "", "RULE_01_PREAUTH_REQ"),
    (("section_b_patient_details", "date_of_discharge"), "2026-02-27", "RULE_02_DATE_CHRONOLOGY"),
    (("section_b_patient_details", "patient_name"), "Ramesh Kumaar", "RULE_05_NAME_MISMATCH"),
    (("section_a_hospital_details", "doctor_registration_no"), None, "RULE_07_DOCTOR_REG_MISSING"),
    (("section_a_hospital_details", "hospital_id_rohini"), " ", "RULE_08_HOSPITAL_ID_MISSING"),
    (("section_e_financial_summary", "total_claimed_amount"), 75000, "RULE_16_ARITHMETIC_TOTAL_MISMATCH"),
    (("section_f_bank_details", "ifsc_code"), None, "RULE_18_BANK_DETAILS_MISSING"),
    (("section_c_ailment_and_treatment", "primary_diagnosis_icd10"), "K3", "RULE_19_ICD_CODE_INVALID"),
])
def test_single_defect_trips_its_rule(path, value, rule):
    r = audit(claim=mutate(path, value))
    assert rule in failed_ids(r)


def test_icd_mismatch_between_documents():
    clin = copy.deepcopy(CLINICAL)
    clin["clinical_assessment"]["primary_icd10_code"] = "K35.2"
    assert "RULE_03_DIAG_PROC_MATCH" in failed_ids(audit(clinical=clin))


def test_short_stay_not_day_care():
    claim = mutate(("section_b_patient_details", "date_of_discharge"), "2026-03-01")
    claim["section_b_patient_details"]["time_of_discharge"] = "20:00"
    clin = copy.deepcopy(CLINICAL)
    clin["hospitalization_timeline"]["discharge_date"] = "2026-03-01"
    assert "RULE_04_MIN_24HR_STAY" in failed_ids(audit(clin, claim))


def test_gender_icd_conflict():
    claim = mutate(("section_c_ailment_and_treatment", "primary_diagnosis_icd10"), "O82")
    r = audit(claim=claim)
    assert "RULE_06_GENDER_CLINIC_MISMATCH" in failed_ids(r)


def test_non_surgeon_without_surgeon_named():
    claim = mutate(("section_a_hospital_details", "qualification"), "MBBS, MD (Medicine)")
    clin = copy.deepcopy(CLINICAL)
    clin["facility"]["treating_doctor"]["qualification"] = "MBBS, MD (Medicine)"
    clin["procedure_details"]["surgeon_name"] = None
    assert "RULE_09_SPECIALTY_MISMATCH" in failed_ids(audit(clin, claim))


def test_duplicate_bill_line():
    lines = CLAIM["section_e_financial_summary"]["itemized_bill_lines"] + [{"description": "CBC", "date": "2026-03-01", "amount": 450}]
    r = audit(claim=mutate(("section_e_financial_summary", "itemized_bill_lines"), lines))
    assert "RULE_10_DUPLICATE_LINE_ITEM" in failed_ids(r)


def test_lump_sum_room_rent():
    lines = [{"description": "Room charges (3 days)", "date": "2026-03-01", "amount": 12000}]
    r = audit(claim=mutate(("section_e_financial_summary", "itemized_bill_lines"), lines))
    assert "RULE_11_UNITEMIZED_ROOM_RENT" in failed_ids(r)


def test_implant_without_invoice():
    clin = copy.deepcopy(CLINICAL)
    clin["procedure_details"]["implant_used"] = True
    assert "RULE_12_IMPLANT_INVOICE_MISSING" in failed_ids(audit(clinical=clin))


def test_bill_line_outside_stay():
    lines = CLAIM["section_e_financial_summary"]["itemized_bill_lines"] + [{"description": "MRI", "date": "2026-02-20", "amount": 6000}]
    assert "RULE_13_DATE_DISCREPANCY_BILL" in failed_ids(audit(claim=mutate(("section_e_financial_summary", "itemized_bill_lines"), lines)))


def test_filing_deadline():
    r = re_.run_claim_audit(CLINICAL, CLAIM, CONFIG, today=date(2026, 3, 30))
    assert "RULE_14_FILING_DEADLINE_RISK" in failed_ids(r)


def test_missing_ot_notes():
    claim = mutate(("section_d_claim_documents_submitted", "operation_theatre_notes"), False)
    assert "RULE_15_MISSING_MANDATORY_DOCS" in failed_ids(audit(claim=claim))


def test_investigation_only_admission():
    claim = copy.deepcopy(CLAIM)
    tr = claim["section_c_ailment_and_treatment"]
    tr.update(procedure_description=None, procedure_icd10_pcs=None, pre_auth_id=None, pre_auth_obtained=False)
    claim["section_e_financial_summary"].update(room_nursing_charges=4000, ot_charges=0, surgeon_consultation_fees=1000,
                                                investigation_charges=14000, medicines_consumables=500, total_claimed_amount=19500)
    clin = copy.deepcopy(CLINICAL)
    clin["procedure_details"].update(procedure_name=None, surgeon_name=None)
    assert "RULE_17_INVESTIGATION_ONLY_FLAG" in failed_ids(audit(clin, claim))


def test_icd_description_mismatch_with_suggestion():
    claim = mutate(("section_c_ailment_and_treatment", "primary_diagnosis_icd10"), "J18.9")
    clin = copy.deepcopy(CLINICAL)
    clin["clinical_assessment"]["primary_icd10_code"] = "J18.9"
    r = audit(clin, claim)
    f = next(f for f in r["findings"] if f["rule_id"] == "RULE_20_ICD_DESCRIPTION_MISMATCH")
    assert f["suggestions"][0]["code"] == "K35.80"


def test_findings_carry_evidence_and_sorted_by_severity():
    claim = mutate(("section_b_patient_details", "patient_name"), "Ramesh Kumaar")
    claim["section_f_bank_details"]["ifsc_code"] = None
    r = audit(claim=claim)
    name = next(f for f in r["findings"] if f["rule_id"] == "RULE_05_NAME_MISMATCH")
    assert {"doc": "claim", "text": "Ramesh Kumaar", "kind": "value"} in name["evidence"]
    sev = [f["severity"] for f in r["findings"]]
    assert sev == sorted(sev, key=["CRITICAL", "MAJOR", "MINOR"].index)


def test_garbage_input_does_not_crash():
    r = re_.run_claim_audit({}, {}, CONFIG, today=TODAY)
    assert 0 <= r["readiness_score"] <= 100 and len(r["checks"]) == 20
