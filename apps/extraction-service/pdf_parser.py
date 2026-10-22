import pymupdf


def extract_text(pdf_bytes: bytes) -> str:
    """
    Extract text directly from a PDF's text layer, page by page.
    Returns an empty/short string if the PDF has no real text layer
    (i.e. it's a scanned image) -- check with is_text_sufficient().
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        pages = [page.get_text() for page in doc]
    finally:
        doc.close()
    return "\n".join(pages).strip()


def is_text_sufficient(text: str, min_chars: int = 50) -> bool:
    """
    Heuristic: if extracted text is very short, this was probably a
    scanned/image PDF with no real text layer -- OCR fallback needed.
    """
    return len(text.strip()) >= min_chars


def extract_words(pdf_bytes: bytes) -> list[list[dict]]:
    """Per page, each word of the text layer with its box as a fraction of the page (0-1).
    Text-layer words are exact, so confidence is 100."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    try:
        for page in doc:
            pw, ph = page.rect.width or 1, page.rect.height or 1
            pages.append([
                {"t": w[4], "x0": w[0] / pw, "y0": w[1] / ph, "x1": w[2] / pw, "y1": w[3] / ph, "c": 100}
                for w in page.get_text("words") if w[4].strip()
            ])
    finally:
        doc.close()
    return pages


def render_pages(pdf_bytes: bytes, dpi: int = 110, max_pages: int = 12, quality: int = 72) -> list[dict]:
    """JPEG previews of each page as data URLs, for the in-browser evidence viewer."""
    import base64
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = []
    try:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pix = page.get_pixmap(dpi=dpi)
            jpg = pix.tobytes(output="jpeg", jpg_quality=quality)
            out.append({"image": "data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii"),
                        "width": pix.width, "height": pix.height})
    finally:
        doc.close()
    return out
