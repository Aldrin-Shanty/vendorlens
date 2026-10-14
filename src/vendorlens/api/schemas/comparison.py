import uuid

from pydantic import BaseModel, Field, model_validator


class CompareSuppliersRequest(BaseModel):
    supplier_ids: list[uuid.UUID] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def validate_unique_suppliers(self):
        if len(self.supplier_ids) != len(set(self.supplier_ids)):
            raise ValueError("Duplicate supplier IDs are not allowed")

        return self
