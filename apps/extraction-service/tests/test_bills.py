"""Bill totals are read off the bill text, and rule 21 compares them with the claimed amount."""
import copy

import pytest

import rules_engine as re_
from bill_totals import find_total
from tests.test_rules import CLAIM, CLINICAL, CONFIG, TODAY


@pytest.mark.parametrize("text,expected", [
    ("FINAL BILL\nRoom rent 12,000\nNet amount payable: 71,000", 71000),
    ("Sub total 2,80,000.00\nGRAND TOTAL Rs. 3,05,020.00", 305020),
    ("Tab Pan 40  120\nTotal  1,250.50", 1250.5),
    ("Bill Date: 04/03/2026\nTotal amount 5000", 5000),
    ("no totals on this page, just 12,000 somewhere", None),
])
def test_find_total(text, expected):
    assert find_total(text) == expected


def audit(bills):
    return {f["rule_id"]: f for f in re_.run_claim_audit(CLINICAL, copy.deepcopy(CLAIM), CONFIG, today=TODAY, bills=bills)["findings"]}


def test_rule21_passes_when_the_claim_matches_the_bills():
    assert "RULE_21_CLAIM_VS_BILLS" not in audit({"hospital_bill": [71000.0], "pharmacy_bill": []})
    # hospital bill + pharmacy bills = claimed (61,500 + 9,500 = 71,000)
    assert "RULE_21_CLAIM_VS_BILLS" not in audit({"hospital_bill": [61500.0], "pharmacy_bill": [4500.0, 5000.0]})


def test_rule21_flags_a_different_amount():
    f = audit({"hospital_bill": [65000.0], "pharmacy_bill": [2000.0]})["RULE_21_CLAIM_VS_BILLS"]
    assert "₹71,000" in f["detected_issue"] and "₹65,000 on the hospital bill" in f["detected_issue"]


def test_rule21_not_applicable_without_bills():
    checks = {c["rule_id"]: c for c in re_.run_claim_audit(CLINICAL, CLAIM, CONFIG, today=TODAY)["checks"]}
    assert checks["RULE_21_CLAIM_VS_BILLS"]["status"] == "not_applicable"
