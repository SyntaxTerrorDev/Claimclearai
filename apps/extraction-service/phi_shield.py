"""PHI shield: mask patient identifiers before any text is sent to an external LLM,
then put the real values back into the structured result.

The LLM only ever sees placeholders like [[NAME_1]] or [[PHONE_2]]. The same value
gets the same placeholder in both documents, so cross-document rules (e.g. name
mismatch) still work after rehydration. A *different* spelling gets a *different*
placeholder, so a genuine mismatch is still caught.
"""
import re
from dataclasses import dataclass, field

TITLE = r"(?:(?i:mr|mrs|ms|miss|master|baby|shri|smt|kum|kumari)\.?\s+)?"
# Words that follow a name on the same line in Indian hospital forms; never part of the name.
STOP = (r"(?!(?:Age|Sex|Gender|DOB|D\.O\.B|Date|UHID|IP|IPD|MRN|Ward|Bed|Room|Policy|Mobile|Phone|Contact|Address|Hospital|Doctor|Dr|Years?|Yrs?|Male|Female|M|F"
        r"|Name|Father|Mother|Husband|Wife|Son|Daughter|Spouse|Guardian|Relation|Relationship|Relative"
        r"|Consultant|Department|Dept|Unit|Admitted|Admission|Discharge|Occupation|Religion|Blood|Marital"
        r"|Nationality|Insured|Insurance|Employer|Reg|Registration|Bill|[SDWC]/O)\b)")
NAME_WORD = STOP + r"[A-Z][A-Za-z'.]*"
NAME_VALUE = TITLE + NAME_WORD + r"(?:[ \t]+" + NAME_WORD + r"){0,3}"

# "Patient Name: ...", "Name of the Insured - ..." etc. Labels are case-insensitive, names must be capitalised.
NAME_LABELS = re.compile(
    r"(?m)\b(?i:(patient(?:'s)?[ \t]*name|name[ \t]+of[ \t]+(?:the[ \t]+)?(?:patient|insured(?:[ \t]+person)?)|"
    r"insured(?:[ \t]+person)?(?:'s)?[ \t]*name|name[ \t]+of[ \t]+(?:the[ \t]+)?proposer|patient))"
    r"[ \t]*[:\-–][ \t]*(" + NAME_VALUE + r")"
)

# Labelled identifiers. Value: 4+ chars of letters/digits with / - separators, containing a digit.
ID_LABELS = re.compile(
    r"(?i)\b(policy[ \t]*(?:no|number|#)|uhid|ip(?:d)?[ \t]*(?:reg(?:istration)?\.?[ \t]*)?(?:no|number)|"
    r"member[ \t]*id|tpa[ \t]*(?:card|id)[ \t]*(?:no|number)?|card[ \t]*(?:no|number)|"
    r"(?:bank[ \t]*)?a/?c[ \t]*(?:no|number)|account[ \t]*(?:no|number)|"
    r"mrn|employee[ \t]*id)(?:[ \t]*(?:no|number|#))?\.?[ \t]*[:\-–#]?[ \t]*((?=[A-Z0-9/\-]*\d)[A-Z0-9][A-Z0-9/\-]{3,})"
)

# Run before ID_LABELS so a spaced Aadhaar ("4521 8890 1123") is masked as one value.
PRE_PATTERNS = [
    ("AADHAAR", re.compile(r"\b[2-9]\d{3}[ \-]?\d{4}[ \-]?\d{4}\b")),
]
PATTERNS = [
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("PAN", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
    ("PHONE", re.compile(r"(?<![\w/])(?:\+91[ \-]?|0)?[6-9]\d{4}[ \-]?\d{5}\b")),
]

PLACEHOLDER = re.compile(r"\[\[\s*([A-Z]+)_(\d+)\s*\]\]")


@dataclass
class Shield:
    by_value: dict = field(default_factory=dict)   # (kind, normalized value) -> placeholder
    by_token: dict = field(default_factory=dict)   # placeholder -> original value
    counts: dict = field(default_factory=dict)

    def token_for(self, kind: str, value: str) -> str:
        key = (kind, re.sub(r"\s+", " ", value.strip().lower()))
        if key not in self.by_value:
            self.counts[kind] = self.counts.get(kind, 0) + 1
            tok = f"[[{kind}_{self.counts[kind]}]]"
            self.by_value[key] = tok
            self.by_token[tok] = value.strip()
        return self.by_value[key]

    # ---------- masking ----------
    def mask(self, text: str) -> str:
        if not text:
            return text
        names = []

        def name_sub(m: re.Match) -> str:
            value = m.group(2).strip()
            names.append(value)
            return m.group(0).replace(value, self.token_for("NAME", value))

        text = NAME_LABELS.sub(name_sub, text)

        # The same name appearing unlabelled elsewhere ("Mr. Ramesh Kumar was admitted...").
        for value in sorted(set(names), key=len, reverse=True):
            bare = re.sub(r"^" + TITLE, "", value, flags=re.I).strip()
            # Also the first two/three words, so the name stays hidden even if extra words were captured.
            words = bare.split()
            variants = {value, bare} | {" ".join(words[:n]) for n in (2, 3) if len(words) > n}
            for v in sorted(variants, key=len, reverse=True):
                if len(v) >= 4:
                    text = re.sub(re.escape(v), self.token_for("NAME", value), text, flags=re.I)

        def id_sub(m: re.Match) -> str:
            value = m.group(2)
            return m.group(0)[: m.start(2) - m.start(0)] + self.token_for("ID", value)

        for kind, rx in PRE_PATTERNS:
            text = rx.sub(lambda m, k=kind: self.token_for(k, m.group(0)), text)
        text = ID_LABELS.sub(id_sub, text)
        for kind, rx in PATTERNS:
            text = rx.sub(lambda m, k=kind: self.token_for(k, m.group(0)), text)
        return text

    # ---------- restoring ----------
    def restore(self, obj):
        """Recursively replace placeholders in the LLM output with the original values."""
        if isinstance(obj, str):
            def sub(m: re.Match) -> str:
                return self.by_token.get(f"[[{m.group(1)}_{m.group(2)}]]", m.group(0))
            return PLACEHOLDER.sub(sub, obj)
        if isinstance(obj, list):
            return [self.restore(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.restore(v) for k, v in obj.items()}
        return obj

    def summary(self) -> dict:
        """Counts only, never values: safe to return to the client or log."""
        return {"masked_total": len(self.by_token), "by_type": dict(self.counts)}


PROMPT_NOTE = (
    "PRIVACY NOTE: personal identifiers in the documents have been replaced with placeholders "
    "such as [[NAME_1]], [[ID_2]] or [[PHONE_1]]. Copy a placeholder exactly, character for character, "
    "into any field whose value it stands for. Never invent or alter placeholders.\n\n"
)
