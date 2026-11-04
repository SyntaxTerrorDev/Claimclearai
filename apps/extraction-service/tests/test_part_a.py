"""Claim form Part A (filled in by the insured): rules 22-25 and the bank account fallback."""
import copy

import rules_engine as re_
from tests.test_rules import CLAIM, CLINICAL, CONFIG, TODAY

PART_A = {"form_present": True, "policy_number": "SH/2026/778812", "company_tpa_id": "TPA-1", "insured_name": "Ramesh Kumar",
          "insured_address": "12 Sector 18, Noida", "insured_phone": "98765 43210", "patient_name": "Mr. Ramesh Kumar",
          "date_of_admission": "2026-03-01", "date_of_discharge": "2026-03-04",
          "hospitalization_expenses": 71000, "post_hospitalization_expenses": 1950, "total_claimed": 72950,
          "bank_account_number": "07901001", "ifsc_code": "UTIB0000079"}

PART_A_RULES = ("RULE_22_POLICY_NUMBER_MISSING", "RULE_23_PART_A_DETAILS_MISMATCH",
                "RULE_24_PART_A_AMOUNT_MISMATCH", "RULE_25_INSURED_CONTACT_MISSING")


def run(**changes):
    claim = copy.deepcopy(CLAIM)
    claim["part_a_insured"] = {**PART_A, **changes}
    r = re_.run_claim_audit(CLINICAL, claim, CONFIG, today=TODAY)
    return {f["rule_id"]: f for f in r["findings"]}, {c["rule_id"]: c["status"] for c in r["checks"]}


def test_clean_part_a_passes():
    findings, checks = run()
    assert not set(PART_A_RULES) & set(findings)
    assert all(checks[r] == "passed" for r in PART_A_RULES)


def test_no_part_a_means_not_applicable():
    checks = {c["rule_id"]: c["status"] for c in re_.run_claim_audit(CLINICAL, CLAIM, CONFIG, today=TODAY)["checks"]}
    assert all(checks[r] == "not_applicable" for r in PART_A_RULES)


def test_missing_policy_number_mentions_the_tpa_id():
    f = run(policy_number=None)[0]["RULE_22_POLICY_NUMBER_MISSING"]
    assert "policy number box in Part A is empty" in f["detected_issue"] and "TPA-1" in f["detected_issue"]
    assert f["ask"] == "you"


def test_part_a_and_b_disagree():
    f = run(patient_name="Ramesh Kumaar", date_of_discharge="2026-03-05")[0]["RULE_23_PART_A_DETAILS_MISMATCH"]
    assert "Ramesh Kumaar" in f["detected_issue"] and "2026-03-05" in f["detected_issue"]


def test_amounts_disagree():
    f = run(hospitalization_expenses=74000, total_claimed=75950)[0]["RULE_24_PART_A_AMOUNT_MISMATCH"]
    assert "₹74,000" in f["detected_issue"] and "₹71,000" in f["detected_issue"]
    f = run(total_claimed=80000)[0]["RULE_24_PART_A_AMOUNT_MISMATCH"]
    assert "add up to ₹72,950" in f["detected_issue"]


def test_missing_contact():
    assert "phone number" in run(insured_phone=None)[0]["RULE_25_INSURED_CONTACT_MISSING"]["detected_issue"]


def test_bank_account_from_part_a_counts():
    claim = copy.deepcopy(CLAIM)
    claim["section_f_bank_details"] = {}
    claim["part_a_insured"] = PART_A
    assert "RULE_18_BANK_DETAILS_MISSING" not in {f["rule_id"] for f in re_.run_claim_audit(CLINICAL, claim, CONFIG, today=TODAY)["findings"]}
