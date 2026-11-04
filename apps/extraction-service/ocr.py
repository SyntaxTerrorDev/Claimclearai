import io
import os
import shutil
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image


def _configure_tesseract() -> None:
    """Find the tesseract binary: TESSERACT_CMD env var > PATH > default Windows install dirs.
    In Docker it is on PATH (apt-get install tesseract-ocr), so nothing changes there."""
    explicit = os.getenv("TESSERACT_CMD")
    if explicit:
        pytesseract.pytesseract.tesseract_cmd = explicit
        return
    if shutil.which("tesseract"):
        return
    for candidate in (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe",
    ):
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


_configure_tesseract()

# Pages are OCR'd several at a time (each Tesseract run is its own process), so keep every run
# single-threaded instead of letting each one try to use all cores.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
OCR_WORKERS = max(1, min(8, (os.cpu_count() or 2) - 1))


def _page_images(pdf_bytes: bytes, dpi: int):
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    zoom = dpi / 72
    matrix = pymupdf.Matrix(zoom, zoom)
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            yield Image.open(io.BytesIO(pix.tobytes("png")))
    finally:
        doc.close()


def ocr_document(pdf_bytes: bytes, dpi: int = 200) -> tuple[str, list[list[dict]]]:
    """One Tesseract pass per page giving both the text (line layout kept) and every word's
    box as a fraction of the page (0-1) with its confidence (0-100), for evidence highlighting."""
    page_texts, pages = ocr_pages(pdf_bytes, dpi)
    return "\n".join(page_texts).strip(), pages


def ocr_pages(pdf_bytes: bytes, dpi: int = 200, on_page=None) -> tuple[list[str], list[list[dict]]]:
    """Like ocr_document, but the text of each page separately. Pages run in parallel
    (OCR_WORKERS at a time); on_page(done, total) is called as each page finishes."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total = doc.page_count
    doc.close()
    futures, pending, done = [], set(), 0
    with ThreadPoolExecutor(OCR_WORKERS) as pool:
        for img in _page_images(pdf_bytes, dpi):
            # keep only a few rendered pages in memory at once
            while len(pending) >= OCR_WORKERS * 2:
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                done += len(finished)
                if on_page:
                    on_page(done, total)
            future = pool.submit(_ocr_image, img)
            futures.append(future)
            pending.add(future)
        while pending:
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            done += len(finished)
            if on_page:
                on_page(done, total)
    results = [f.result() for f in futures]
    return [text for text, _ in results], [words for _, words in results]


def _ocr_image(img) -> tuple[str, list[dict]]:
    """(page text with line layout, word boxes) for one rendered page."""
    w, h = img.size
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    words, lines, current_key, current = [], [], None, []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key != current_key and current:
            lines.append(" ".join(current))
            current = []
        current_key = key
        current.append(text)
        x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append({"t": text, "x0": x / w, "y0": y / h, "x1": (x + bw) / w, "y1": (y + bh) / h, "c": round(conf)})
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines), words


def extract_text_ocr(pdf_bytes: bytes, dpi: int = 200) -> str:
    return ocr_document(pdf_bytes, dpi)[0]
