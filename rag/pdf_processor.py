from rag.config import UserFacingError
"""Read selectable text without persisting uploaded PDFs."""
from io import BytesIO
from pathlib import PurePath
from pypdf import PdfReader

def extract_text_from_pdf(uploaded_file):
    name = PurePath(uploaded_file.name.replace("\\", "/")).name
    data = uploaded_file.getvalue()
    if not data or len(data) > 20 * 1024 * 1024:
        raise UserFacingError("Each PDF must be nonempty and no larger than 20 MB.")
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            raise UserFacingError("Password-protected PDFs are not supported.")
        if len(reader.pages) > 300:
            raise UserFacingError("Each PDF may contain at most 300 pages.")
        pages = []
        for number, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append({"text": text, "source": name, "page_number": number})
    except ValueError:
        raise
    except Exception:
        raise UserFacingError("Could not read the PDF. Upload a valid, unencrypted PDF.") from None
    if not pages:
        raise UserFacingError("A PDF has no selectable text. Run OCR on scanned documents first.")
    return pages

def extract_text_from_multiple_pdfs(uploaded_files):
    if not uploaded_files or len(uploaded_files) > 10:
        raise UserFacingError("Upload between 1 and 10 PDFs.")
    names = [PurePath(f.name.replace("\\", "/")).name for f in uploaded_files]
    if len(set(names)) != len(names):
        raise UserFacingError("PDF filenames must be unique so sources can be distinguished.")
    return [page for file in uploaded_files for page in extract_text_from_pdf(file)]
