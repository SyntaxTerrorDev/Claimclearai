from phi_shield import Shield
import icd10

CLINICAL = """CITY CARE HOSPITAL - DISCHARGE SUMMARY
Patient Name : Mr. Ramesh Kumar   Age: 45   Sex: M
UHID: CC-2026-00917   IPD No: 4471
Mr. Ramesh Kumar was admitted with acute appendicitis. Contact 98765 43210, ramesh.k@gmail.com
Treating doctor: Dr. Anil Mehta, MS (General Surgery), Reg No. DMC/45821
Policy number: not available"""
CLAIM = """CLAIM FORM PART B
Name of the Patient: Ramesh Kumaar
IP Registration Number: 4471   Policy No: SH/2026/778812
Bank A/c No: 123456789012  IFSC: SBIN0001234  Aadhaar 4521 8890 1123  PAN ABCDE1234F"""


def test_identifiers_never_reach_llm_text():
    s = Shield()
    masked = s.mask(CLINICAL) + s.mask(CLAIM)
    for secret in ("Ramesh", "98765", "ramesh.k@", "778812", "123456789012", "4521 8890 1123", "ABCDE1234F", "CC-2026-00917"):
        assert secret not in masked
    # non-patient data the rules need stays readable
    for keep in ("Anil Mehta", "DMC/45821", "SBIN0001234", "not available", "Age: 45"):
        assert keep in masked
    assert s.summary()["masked_total"] >= 9
    assert "Ramesh" not in str(s.summary())


def test_same_value_same_token_different_spelling_different_token():
    s = Shield()
    c, k = s.mask(CLINICAL), s.mask(CLAIM)
    assert "IPD No: [[ID_2]]" in c and "IP Registration Number: [[ID_2]]" in k
    name_tokens = {t for t, v in s.by_token.items() if t.startswith("[[NAME")}
    assert len(name_tokens) == 2  # "Ramesh Kumar" vs "Ramesh Kumaar" -> mismatch survives masking


def test_restore_round_trip_tolerates_llm_spacing():
    s = Shield()
    s.mask(CLAIM)
    out = s.restore({"n": "[[NAME_1]]", "ids": ["[[ ID_2 ]]"], "x": 5, "unknown": "[[NAME_99]]"})
    assert out == {"n": "Ramesh Kumaar", "ids": ["SH/2026/778812"], "x": 5, "unknown": "[[NAME_99]]"}


def test_icd_helpers():
    assert icd10.normalize(" k3580 ") == "K35.80"
    assert icd10.is_valid_format("S72.001A") and not icd10.is_valid_format("123")
    assert icd10.chapter("O82")[0] == 15
    assert icd10.sex_conflict("N40.0", "Female") and icd10.sex_conflict("N40.0", "Male") is None
    assert icd10.age_conflict("P59.9", 30) and icd10.age_conflict("P59.9", 0) is None
    assert icd10.suggest("Cholelithiasis with biliary colic")[0]["code"] == "K80.20"
    assert icd10.description_mismatch("K35.2", "acute appendicitis") is None
