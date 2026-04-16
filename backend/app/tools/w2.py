from app.ingest.pipeline import ingest_w2
from app.schemas.documents import ParsedDocument
from app.tools.document_store import get_store


class DocumentNotFoundError(KeyError):
    pass


def parse_w2(document_id: str, default_tax_year: int) -> ParsedDocument:
    stored = get_store().get(document_id)
    if stored is None:
        raise DocumentNotFoundError(
            f"Document '{document_id}' not found. Upload it first."
        )
    result = ingest_w2(
        pdf_bytes=stored.pdf_bytes,
        document_id=stored.document_id,
        source_path=stored.source_path,
        default_tax_year=default_tax_year,
    )
    return result.parsed
