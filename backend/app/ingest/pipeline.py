"""PDF ingest pipeline.

Strategy:
1. Try pdfplumber text extraction. If text is present and extraction confidence is
   high enough, we're done — cheap and accurate for digital PDFs.
2. Otherwise, rasterize pages with pypdfium2 and OCR with pytesseract. Slower but
   handles scans and image-only PDFs.

The pipeline is a single function because the decision (digital vs. OCR) is
internal — callers just pass bytes and get a W2Form or an IngestError.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO

import pdfplumber
import pypdfium2 as pdfium
import pytesseract
from PIL import Image

from app.schemas.documents import IngestError, ParsedDocument, W2Form
from app.ingest.w2_extractor import ExtractionResult, extract_w2_fields, require_w2

OCR_DPI = 300
PDFPLUMBER_CONFIDENCE_THRESHOLD = 0.45

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'



@dataclass
class IngestResult:
    parsed: ParsedDocument
    ocr_used: bool


def _text_from_pdfplumber(pdf_bytes: bytes) -> str:
    parts: list[str] = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t:
                parts.append(t)
    return "\n".join(parts)


def _render_pages_to_images(pdf_bytes: bytes, dpi: int = OCR_DPI) -> list[Image.Image]:
    # pypdfium2 is faster than PyMuPDF for rasterization and has no GPL issues.
    doc = pdfium.PdfDocument(pdf_bytes)
    scale = dpi / 72.0
    images: list[Image.Image] = []
    for page in doc:
        bitmap = page.render(scale=scale)
        pil = bitmap.to_pil()
        images.append(pil.convert("RGB"))
    doc.close()
    return images


def _text_from_ocr(pdf_bytes: bytes) -> str:
    images = _render_pages_to_images(pdf_bytes)
    # PSM 6 = assume a single uniform block of text. Best default for W-2 layout.
    return "\n".join(
        pytesseract.image_to_string(img, lang="eng", config="--psm 6") for img in images
    )


def ingest_w2(
    pdf_bytes: bytes,
    document_id: str,
    source_path: str,
    default_tax_year: int,
) -> IngestResult:
    """Two-stage ingest. Returns a ParsedDocument; raises IngestError on critical failure."""
    ocr_used = False

    digital_text = _text_from_pdfplumber(pdf_bytes)
    result: ExtractionResult | None = None
    if digital_text.strip():
        result = extract_w2_fields(digital_text, document_id, default_tax_year)

    if result is None or result.confidence < PDFPLUMBER_CONFIDENCE_THRESHOLD:
        ocr_text = _text_from_ocr(pdf_bytes)
        if not ocr_text.strip():
            raise IngestError("OCR produced no text", missing_fields=["all"])
        ocr_result = extract_w2_fields(ocr_text, document_id, default_tax_year)
        # Take whichever result has higher confidence — sometimes pdfplumber grabs
        # a partial text layer and OCR fills the rest.
        if result is None or ocr_result.confidence > result.confidence:
            result = ocr_result
            ocr_used = True

    w2 = require_w2(result)

    return IngestResult(
        parsed=ParsedDocument(
            document_id=document_id,
            kind="w2",
            source_path=source_path,
            parsed_at=datetime.now(timezone.utc),
            w2=w2,
            ocr_used=ocr_used,
            confidence=result.confidence,
        ),
        ocr_used=ocr_used,
    )


# Exposed for test injection — lets tests skip real PDF/OCR and just hand over text.
def ingest_w2_from_text(
    text: str,
    document_id: str,
    source_path: str,
    default_tax_year: int,
    ocr_used: bool = False,
) -> ParsedDocument:
    result = extract_w2_fields(text, document_id, default_tax_year)
    w2 = require_w2(result)
    return ParsedDocument(
        document_id=document_id,
        kind="w2",
        source_path=source_path,
        parsed_at=datetime.now(timezone.utc),
        w2=w2,
        ocr_used=ocr_used,
        confidence=result.confidence,
    )


__all__ = ["IngestResult", "ingest_w2", "ingest_w2_from_text"]


# Re-export so tool wrapper can import without reaching into the schemas module directly
_W2Form = W2Form
