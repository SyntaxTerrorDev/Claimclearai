import io
import pymupdf
import pytesseract
from PIL import Image
import platform

# Point pytesseract directly to your Windows installation

if platform.system() == "Windows":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extract_text_ocr(pdf_bytes: bytes, dpi: int = 200) -> str:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    zoom = dpi / 72
    matrix = pymupdf.Matrix(zoom, zoom)

    pages_text = []
    try:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            pages_text.append(pytesseract.image_to_string(img))
    finally:
        doc.close()

    return "\n".join(pages_text).strip()