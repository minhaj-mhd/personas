import logging
from io import BytesIO

from pypdf import PdfReader

logger = logging.getLogger(__name__)


class DocumentExtractionError(Exception):
    """Raised when text cannot be extracted from an uploaded document."""


def extract_pdf_text(data: bytes) -> str:
    """
    Extracts plain text from PDF bytes, joining pages with blank lines.
    Raises DocumentExtractionError for unreadable, encrypted, or image-only PDFs.
    """
    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            # PDFs "encrypted" with an empty owner password are still readable
            reader.decrypt("")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except DocumentExtractionError:
        raise
    except Exception as e:
        logger.error(f"Failed to parse PDF: {e}")
        raise DocumentExtractionError(
            "Could not read the PDF. It may be corrupted or password-protected."
        ) from e

    text = "\n\n".join(p for p in pages if p)
    if not text:
        raise DocumentExtractionError(
            "No extractable text found in the PDF. It may be a scanned/image-only document."
        )
    return text


def extract_upload_text(filename: str, content_type: str | None, data: bytes) -> str:
    """
    Extracts text from an uploaded file: PDFs via pypdf, everything else as UTF-8 text.
    Raises DocumentExtractionError for unsupported binary formats.
    """
    is_pdf = filename.lower().endswith(".pdf") or content_type == "application/pdf"
    if is_pdf:
        return extract_pdf_text(data)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise DocumentExtractionError(
            "Unsupported file type. Upload a .txt, .md, or .pdf file."
        ) from e
