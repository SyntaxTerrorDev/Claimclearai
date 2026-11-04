"""Read the total off a hospital or pharmacy bill.

Pattern matching on the bill's text, no LLM call: bills never leave this server. The amount must
be on the same line as a total label ("Grand Total", "Net Amount Payable", ...); the strongest
label wins, and the largest amount on those lines is taken as the bill's total.
"""
import re

STRONG = re.compile(r"(grand\s*total|net\s*(?:amount|payable|bill(?:\s*amount)?|total)|amount\s*payable|"
                    r"total\s*payable|bill\s*amount|total\s*(?:bill\s*)?amount|final\s*amount)", re.I)
WEAK = re.compile(r"\btotal\b", re.I)
# 3,05,020 / 305,020 / 305020.00 (no dates: those contain / or -)
AMOUNT = re.compile(r"(?<![\d.,/-])(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d{2,8}(?:\.\d{1,2})?)(?![\d,/-])")
MAX_AMOUNT = 10_000_000  # anything bigger is a misread (or an ID number)


def find_total(text: str) -> float | None:
    """The bill's total in rupees, or None if no total line could be read."""
    for label in (STRONG, WEAK):
        amounts = []
        for line in text.splitlines():
            m = label.search(line)
            if m:
                amounts += [v for v in (float(a.replace(",", "")) for a in AMOUNT.findall(line[m.end():])) if 0 < v < MAX_AMOUNT]
        if amounts:
            return max(amounts)
    return None
