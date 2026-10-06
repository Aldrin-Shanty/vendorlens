import uuid

from pydantic import BaseModel , Field


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)
class SearchResultRead(BaseModel):
    chunk_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str
    document_version_id: uuid.UUID
    filename: str
    page_number: int
    text: str
    distance: float

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

class CitationRead(BaseModel):
    chunk_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str
    document_version_id: uuid.UUID
    filename: str
    page_number: int
    text: str

class AskResponse(BaseModel):
    answer: str
    retrieved_evidence: list[CitationRead]
