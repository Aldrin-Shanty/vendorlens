from pathlib import Path

from sqlalchemy.orm import Session

from vendorlens.db.models.chunk import Chunk
from vendorlens.db.models.document_version import DocumentVersion
from vendorlens.services.chunking import chunk_pages
from vendorlens.services.pdf_parser import parse_pdf
from vendorlens.services.embeddings import embed_text


def ingest_document_version(
    db: Session,
    document_version: DocumentVersion,
    path: Path,
) -> int:
    pages = parse_pdf(path)

    text_chunks = chunk_pages(pages)

    for text_chunk in text_chunks:
        chunk = Chunk(
            document_version_id=document_version.id,
            page_number=text_chunk.page_number,
            chunk_index=text_chunk.chunk_index,
            text=text_chunk.text,
            embedding=embed_text(text_chunk.text),
        )

        db.add(chunk)

    return len(text_chunks)
