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


# --- regressions reported by CodeRabbit on PR #10 ---

def test_name_followed_by_another_header_is_still_masked_everywhere():
    s = Shield()
    text = ("Patient Name: Ramesh Kumar Father's Name: Suresh Kumar\n"
            "Consultant: Dr. Anil Mehta\n"
            "Mr. Ramesh Kumar was admitted with pain abdomen. RAMESH KUMAR was stable.")
    masked = s.mask(text)
    assert "Ramesh" not in masked and "RAMESH" not in masked
    assert s.by_token["[[NAME_1]]"] == "Ramesh Kumar"  # restored value has no extra words
    assert "Anil Mehta" in masked  # the doctor is not patient data


def test_relation_markers_end_the_name():
    s = Shield()
    masked = s.mask("Name of the Patient: Balvinder Kumar S/O Mohan Lal\nBalvinder Kumar admitted on 01/07/2024")
    assert "Balvinder" not in masked
    assert s.by_token["[[NAME_1]]"] == "Balvinder Kumar"


def test_long_capture_still_hides_first_words():
    s = Shield()
    masked = s.mask("Patient: Ramesh Kumar Singh Yadav\nLater, Ramesh Kumar was shifted to the ward.")
    assert "Ramesh Kumar" not in masked


def test_id_labels_with_no_suffix_and_reg_period():
    s = Shield()
    masked = s.mask("UHID No: CC-2026-00917\nIPD Reg. No: 4471\nMRN No.: 55123\nMember ID No: MB778812\nPolicy Number: SH/2026/7788")
    for secret in ("CC-2026-00917", "4471", "55123", "MB778812", "SH/2026/7788"):
        assert secret not in masked, secret


def test_covid_u_code_is_valid():
    assert icd10.is_valid_format("U07.1")
    assert icd10.chapter("U07.1")[0] == 22
