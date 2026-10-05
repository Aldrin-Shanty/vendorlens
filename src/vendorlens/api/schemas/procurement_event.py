import uuid

from pydantic import BaseModel, Field


class ProcurementEventCreate(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=200,
    )


class ProcurementEventRead(BaseModel):
    id: uuid.UUID
    title: str


class ProcurementEventUpdate(BaseModel):
    title: str = Field(
        min_length=1,
        max_length=200,
    )
