import uuid

from pydantic import BaseModel


class ProposalCreate(BaseModel):
    supplier_id: uuid.UUID
    procurement_event_id: uuid.UUID


class ProposalRead(BaseModel):
    id: uuid.UUID
    supplier_id: uuid.UUID
    procurement_event_id: uuid.UUID
