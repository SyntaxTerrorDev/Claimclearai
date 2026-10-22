"""ICD-10 code intelligence for the rules engine.

- normalize / validate the code format (WHO ICD-10 and ICD-10-CM style)
- map a code to its chapter
- sex- and age-specific code ranges (e.g. obstetric codes on a male patient)
- suggest likely codes from free-text diagnosis, using a curated list of
  common inpatient diagnoses in Indian hospitals (offline, no API needed)
"""
import re

CODE_RX = re.compile(r"^[A-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?$")  # U = special purposes (e.g. U07.1 COVID-19)

# (first, last, chapter number, title) on the 3-character category.
CHAPTERS = [
    ("A00", "B99", 1, "Certain infectious and parasitic diseases"),
    ("C00", "D49", 2, "Neoplasms"),
    ("D50", "D89", 3, "Diseases of the blood and immune mechanism"),
    ("E00", "E89", 4, "Endocrine, nutritional and metabolic diseases"),
    ("F01", "F99", 5, "Mental and behavioural disorders"),
    ("G00", "G99", 6, "Diseases of the nervous system"),
    ("H00", "H59", 7, "Diseases of the eye and adnexa"),
    ("H60", "H95", 8, "Diseases of the ear and mastoid process"),
    ("I00", "I99", 9, "Diseases of the circulatory system"),
    ("J00", "J99", 10, "Diseases of the respiratory system"),
    ("K00", "K95", 11, "Diseases of the digestive system"),
    ("L00", "L99", 12, "Diseases of the skin and subcutaneous tissue"),
    ("M00", "M99", 13, "Diseases of the musculoskeletal system"),
    ("N00", "N99", 14, "Diseases of the genitourinary system"),
    ("O00", "O9A", 15, "Pregnancy, childbirth and the puerperium"),
    ("P00", "P96", 16, "Certain conditions originating in the perinatal period"),
    ("Q00", "Q99", 17, "Congenital malformations"),
    ("R00", "R99", 18, "Symptoms, signs and abnormal findings"),
    ("S00", "T88", 19, "Injury, poisoning and external causes"),
    ("V00", "Y99", 20, "External causes of morbidity"),
    ("Z00", "Z99", 21, "Factors influencing health status"),
]

FEMALE_ONLY = [("O00", "O9A", "pregnancy/childbirth"), ("N70", "N98", "female genital organs"),
               ("C51", "C58", "female genital cancer"), ("D25", "D28", "benign uterine/ovarian tumour"),
               ("Z32", "Z37", "pregnancy-related encounter"), ("Z39", "Z39", "postpartum care")]
MALE_ONLY = [("N40", "N53", "male genital organs"), ("C60", "C63", "male genital cancer"),
             ("D29", "D29", "benign male genital tumour")]
NEWBORN_ONLY = [("P00", "P96", "perinatal condition"), ("Z38", "Z38", "liveborn infant")]

# Keyword groups -> codes. Each entry: code, description, keywords (all lowercase).
COMMON = [
    ("K35.80", "Acute appendicitis", ["appendicitis", "appendix"]),
    ("K80.20", "Calculus of gallbladder without cholecystitis", ["cholelithiasis", "gallstone", "gall stone", "gallbladder stone"]),
    ("K81.0", "Acute cholecystitis", ["cholecystitis"]),
    ("K40.90", "Inguinal hernia, unilateral, without obstruction", ["inguinal hernia", "hernia"]),
    ("K29.70", "Gastritis, unspecified", ["gastritis"]),
    ("K92.2", "Gastrointestinal haemorrhage, unspecified", ["gi bleed", "gastrointestinal bleed", "melena", "haematemesis", "hematemesis"]),
    ("K85.90", "Acute pancreatitis, unspecified", ["pancreatitis"]),
    ("K74.60", "Cirrhosis of liver, unspecified", ["cirrhosis"]),
    ("A09", "Infectious gastroenteritis and colitis", ["gastroenteritis", "diarrhoea", "diarrhea", "acute gastroenteritis"]),
    ("A01.0", "Typhoid fever", ["typhoid", "enteric fever"]),
    ("A90", "Dengue fever", ["dengue"]),
    ("A91", "Dengue haemorrhagic fever", ["dengue haemorrhagic", "dengue hemorrhagic", "dhf"]),
    ("B50.9", "Plasmodium falciparum malaria", ["falciparum", "malaria"]),
    ("A41.9", "Sepsis, unspecified organism", ["sepsis", "septicaemia", "septicemia"]),
    ("A15.0", "Tuberculosis of lung", ["tuberculosis", "pulmonary tb", "koch"]),
    ("U07.1", "COVID-19", ["covid", "sars-cov-2"]),
    ("J18.9", "Pneumonia, unspecified organism", ["pneumonia", "lrti"]),
    ("J44.1", "COPD with acute exacerbation", ["copd", "chronic obstructive"]),
    ("J45.909", "Asthma, unspecified", ["asthma", "bronchial asthma"]),
    ("J06.9", "Acute upper respiratory infection", ["urti", "upper respiratory"]),
    ("I21.9", "Acute myocardial infarction, unspecified", ["myocardial infarction", "heart attack", "stemi", "nstemi", "ami"]),
    ("I20.0", "Unstable angina", ["unstable angina", "angina"]),
    ("I25.10", "Coronary artery disease", ["coronary artery disease", "cad", "ihd", "ischaemic heart", "ischemic heart"]),
    ("I10", "Essential (primary) hypertension", ["hypertension", "htn", "high blood pressure"]),
    ("I50.9", "Heart failure, unspecified", ["heart failure", "ccf", "chf"]),
    ("I48.91", "Atrial fibrillation", ["atrial fibrillation", "af "]),
    ("I63.9", "Cerebral infarction (ischaemic stroke)", ["stroke", "cva", "cerebral infarction"]),
    ("I61.9", "Intracerebral haemorrhage", ["intracerebral haemorrhage", "intracerebral hemorrhage", "ich"]),
    ("E11.9", "Type 2 diabetes mellitus without complications", ["type 2 diabetes", "t2dm", "diabetes mellitus", "dm"]),
    ("E11.65", "Type 2 diabetes with hyperglycaemia", ["hyperglycaemia", "hyperglycemia", "uncontrolled diabetes"]),
    ("E10.10", "Type 1 diabetes with ketoacidosis", ["dka", "diabetic ketoacidosis", "ketoacidosis"]),
    ("E86.0", "Dehydration", ["dehydration"]),
    ("E87.1", "Hyponatraemia", ["hyponatremia", "hyponatraemia"]),
    ("N39.0", "Urinary tract infection, site not specified", ["urinary tract infection", "uti"]),
    ("N20.0", "Calculus of kidney", ["renal calculus", "kidney stone", "nephrolithiasis", "renal stone"]),
    ("N20.1", "Calculus of ureter", ["ureteric calculus", "ureteric stone", "ureterolithiasis"]),
    ("N17.9", "Acute kidney failure, unspecified", ["acute kidney injury", "aki", "acute renal failure"]),
    ("N18.6", "End stage renal disease", ["esrd", "end stage renal", "ckd 5", "chronic kidney disease"]),
    ("N40.0", "Benign prostatic hyperplasia", ["bph", "benign prostatic", "prostatic hyperplasia", "prostate enlargement"]),
    ("N80.0", "Endometriosis of uterus", ["endometriosis"]),
    ("D25.9", "Leiomyoma of uterus, unspecified", ["fibroid", "leiomyoma", "myoma"]),
    ("N83.20", "Ovarian cyst, unspecified", ["ovarian cyst"]),
    ("O80", "Encounter for full-term uncomplicated delivery", ["normal delivery", "nvd", "vaginal delivery", "full term delivery"]),
    ("O82", "Encounter for caesarean delivery", ["caesarean", "cesarean", "c-section", "lscs"]),
    ("O14.90", "Pre-eclampsia", ["pre-eclampsia", "preeclampsia"]),
    ("O24.410", "Gestational diabetes", ["gestational diabetes", "gdm"]),
    ("C50.919", "Malignant neoplasm of breast", ["breast cancer", "carcinoma breast", "ca breast"]),
    ("C61", "Malignant neoplasm of prostate", ["prostate cancer", "carcinoma prostate", "ca prostate"]),
    ("C53.9", "Malignant neoplasm of cervix uteri", ["cervical cancer", "carcinoma cervix", "ca cervix"]),
    ("C34.90", "Malignant neoplasm of lung", ["lung cancer", "carcinoma lung", "ca lung"]),
    ("C18.9", "Malignant neoplasm of colon", ["colon cancer", "colorectal", "carcinoma colon"]),
    ("S72.001A", "Fracture of neck of femur", ["neck of femur", "hip fracture", "femur fracture", "fracture femur"]),
    ("S52.501A", "Fracture of lower end of radius", ["distal radius", "colles", "radius fracture"]),
    ("S82.201A", "Fracture of shaft of tibia", ["tibia fracture", "fracture tibia"]),
    ("S06.0X0A", "Concussion", ["concussion", "head injury"]),
    ("T14.90", "Injury, unspecified", ["injury", "trauma", "rta", "road traffic accident"]),
    ("T63.001A", "Snake venom poisoning", ["snake bite", "snakebite"]),
    ("M17.11", "Primary osteoarthritis, right knee", ["osteoarthritis knee", "knee osteoarthritis", "oa knee"]),
    ("M51.26", "Lumbar disc displacement", ["disc prolapse", "pivd", "disc herniation", "slipped disc"]),
    ("H25.9", "Age-related cataract", ["cataract"]),
    ("G40.909", "Epilepsy, unspecified", ["epilepsy", "seizure", "convulsion"]),
    ("G45.9", "Transient cerebral ischaemic attack", ["tia", "transient ischemic", "transient ischaemic"]),
    ("F10.239", "Alcohol dependence with withdrawal", ["alcohol withdrawal", "alcohol dependence"]),
    ("L03.90", "Cellulitis, unspecified", ["cellulitis"]),
    ("L02.91", "Cutaneous abscess, unspecified", ["abscess"]),
    ("R50.9", "Fever, unspecified", ["fever", "pyrexia"]),
    ("R10.9", "Unspecified abdominal pain", ["abdominal pain", "pain abdomen"]),
    ("R55", "Syncope and collapse", ["syncope", "collapse"]),
    ("P59.9", "Neonatal jaundice, unspecified", ["neonatal jaundice", "neonatal hyperbilirubinemia"]),
    ("P07.30", "Preterm newborn", ["preterm", "premature baby"]),
]
COMMON_BY_CODE = {c: d for c, d, _ in COMMON}


def normalize(code: str | None) -> str:
    """'k35.80 ' -> 'K35.80', 'K3580' -> 'K35.80'. Returns '' for empty input."""
    if not code:
        return ""
    c = re.sub(r"[\s]", "", str(code)).upper().rstrip(".")
    if len(c) > 3 and "." not in c:
        c = c[:3] + "." + c[3:]
    return c


def is_valid_format(code: str) -> bool:
    return bool(CODE_RX.match(normalize(code)))


def category(code: str) -> str:
    return normalize(code)[:3]


def _in(cat: str, lo: str, hi: str) -> bool:
    return lo <= cat <= hi


def chapter(code: str):
    cat = category(code)
    if cat.startswith("U"):
        return (22, "Codes for special purposes (COVID-19)")
    for lo, hi, num, title in CHAPTERS:
        if _in(cat, lo, hi):
            return (num, title)
    return None


def sex_conflict(code: str, gender: str | None) -> str | None:
    """Return a reason string if the code is restricted to the other sex."""
    g = (gender or "").strip().lower()
    if not g:
        return None
    is_male = g in ("m", "male", "man", "boy")
    is_female = g in ("f", "female", "woman", "girl")
    cat = category(code)
    if is_male:
        for lo, hi, what in FEMALE_ONLY:
            if _in(cat, lo, hi):
                return f"{normalize(code)} is a {what} code (female only), but the patient is recorded as male."
    if is_female:
        for lo, hi, what in MALE_ONLY:
            if _in(cat, lo, hi):
                return f"{normalize(code)} is a {what} code (male only), but the patient is recorded as female."
    return None


def age_conflict(code: str, age) -> str | None:
    try:
        a = float(age)
    except (TypeError, ValueError):
        return None
    cat = category(code)
    for lo, hi, what in NEWBORN_ONLY:
        if _in(cat, lo, hi) and a >= 1:
            return f"{normalize(code)} is a {what} code (newborns only), but the patient is {a:g} years old."
    if _in(cat, "O00", "O9A") and (a < 10 or a > 60):
        return f"{normalize(code)} is an obstetric code, implausible for a patient aged {a:g}."
    return None


def suggest(description: str | None, limit: int = 3) -> list[dict]:
    """Rank curated codes by keyword hits in the diagnosis text."""
    text = " " + re.sub(r"[^a-z0-9\- ]", " ", (description or "").lower()) + " "
    if not text.strip():
        return []
    scored = []
    for code, desc, kws in COMMON:
        hits = [k for k in kws if f" {k.strip()} " in text or (len(k) > 5 and k in text)]
        if hits:
            scored.append((max(len(k) for k in hits) + 3 * len(hits), code, desc))
    scored.sort(reverse=True)
    return [{"code": c, "description": d} for _, c, d in scored[:limit]]


def description_mismatch(code: str, description: str | None) -> dict | None:
    """If the diagnosis text clearly points to a different chapter than the code, explain why."""
    sugg = suggest(description, limit=3)
    if not sugg or not is_valid_format(code):
        return None
    if any(category(s["code"]) == category(code) for s in sugg):
        return None
    ch_code, ch_sugg = chapter(code), chapter(sugg[0]["code"])
    if ch_code and ch_sugg and ch_code[0] == ch_sugg[0]:
        return None  # same body system: plausible sub-coding difference, don't flag
    return {"suggestions": sugg, "code_chapter": ch_code[1] if ch_code else "unknown chapter"}
