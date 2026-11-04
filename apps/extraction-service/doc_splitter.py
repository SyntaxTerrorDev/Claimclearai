"""Split one merged PDF (everything the hospital handed over, in a single file) into its documents.

Every page is classified on its own. A page starts a new document only when its title clearly
names a different document type (a strong phrase near the top of the page); every other page,
such as page 2 of a bill, stays with the document before it. A normal multi-page document
therefore comes back as one part.
"""
import pymupdf

import doc_classifier

# A strong phrase in the page's title area scores 3 x 3 = 9 (see doc_classifier).
START_SCORE = 9


def split_ranges(page_texts: list[str]) -> list[tuple[int, int]]:
    """[(first page, last page)] for each document found, 0-based and inclusive."""
    parts: list[list] = []  # [first, last, type]
    for i, text in enumerate(page_texts):
        kind, scores = doc_classifier.classify(text)
        starts_new = kind != doc_classifier.OTHER and scores[kind] >= START_SCORE
        if not parts or (starts_new and kind != parts[-1][2]):
            parts.append([i, i, kind if starts_new else doc_classifier.OTHER])
        else:
            parts[-1][1] = i
            if parts[-1][2] == doc_classifier.OTHER and starts_new:
                parts[-1][2] = kind
    return [(first, last) for first, last, _ in parts]


def page_subset(pdf_bytes: bytes, first: int, last: int) -> bytes:
    """A new PDF holding pages first..last (0-based, inclusive)."""
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = pymupdf.open()
    try:
        out.insert_pdf(src, from_page=first, to_page=last)
        return out.tobytes()
    finally:
        out.close()
        src.close()


def part_name(name: str, first: int, last: int) -> str:
    return f"{name} (page {first + 1})" if first == last else f"{name} (pages {first + 1}\u2013{last + 1})"
