from dataclasses import dataclass
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.db.models.chunk import Chunk
from vendorlens.db.models.document import Document
from vendorlens.db.models.document_version import DocumentVersion
from vendorlens.db.models.proposal import Proposal
from vendorlens.db.models.supplier import Supplier
from vendorlens.services.embeddings import embed_text


@dataclass
class SearchResult:
    chunk_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str
    document_version_id: uuid.UUID
    filename: str
    page_number: int
    text: str
    distance: float


def semantic_search(
    db: Session,
    procurement_event_id: uuid.UUID,
    query: str,
    limit: int = 5,
) -> list[SearchResult]:
    query_embedding = embed_text(query)

    distance = Chunk.embedding.cosine_distance(query_embedding)

    statement = (
        select(
            Chunk.id,
            Supplier.id,
            Supplier.name,
            DocumentVersion.id,
            DocumentVersion.filename,
            Chunk.page_number,
            Chunk.text,
            distance,
        )
        .join(
            DocumentVersion,
            Chunk.document_version_id == DocumentVersion.id,
        )
        .join(
            Document,
            DocumentVersion.document_id == Document.id,
        )
        .join(
            Proposal,
            Document.proposal_id == Proposal.id,
        )
        .join(
            Supplier,
            Proposal.supplier_id == Supplier.id,
        )
        .where(
            Proposal.procurement_event_id == procurement_event_id,
            Chunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(limit)
    )

    rows = db.execute(statement).all()

    return [
        SearchResult(
            chunk_id=row[0],
            supplier_id=row[1],
            supplier_name=row[2],
            document_version_id=row[3],
            filename=row[4],
            page_number=row[5],
            text=row[6],
            distance=row[7],
        )
        for row in rows
    ]
