import uuid
from pydantic import BaseModel,Field


class SupplierCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200
    )

class SupplierRead(BaseModel):
    id: uuid.UUID
    name: str

class SupplierUpdate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200
    )
