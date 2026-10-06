from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.db.models.chunk import Chunk
from vendorlens.services.embeddings import embed_text


def semantic_search(
    db: Session,
    query: str,
    limit: int = 5,
) -> list[Chunk]:
    query_embedding = embed_text(query)

    statement = (
        select(Chunk)
        .where(Chunk.embedding.is_not(None))
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )

    return list(db.scalars(statement).all())
