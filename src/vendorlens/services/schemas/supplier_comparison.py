import uuid

from pydantic import BaseModel, Field, model_validator


class FactEvidence(BaseModel):
    evidence_ids: list[int] = Field(min_length=1)


class SupplierFacts(BaseModel):
    supplier_name: str = Field(min_length=1)

    unit_price: float | None = Field(default=None, ge=0)
    currency: str | None = None
    unit_price_evidence: FactEvidence | None = None

    warranty_years: float | None = Field(default=None, ge=0)
    warranty_evidence: FactEvidence | None = None

    delivery_days: int | None = Field(default=None, ge=0)
    delivery_evidence: FactEvidence | None = None

    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_facts(self):
        if (self.unit_price is None) != (self.currency is None):
            raise ValueError(
                "Unit price and currency must be provided together"
            )

        pairs = [
            (self.unit_price, self.unit_price_evidence, "unit_price"),
            (self.warranty_years, self.warranty_evidence, "warranty_years"),
            (self.delivery_days, self.delivery_evidence, "delivery_days"),
        ]

        for value, evidence, field_name in pairs:
            if value is not None and evidence is None:
                raise ValueError(f"{field_name} requires evidence")

            if value is None and evidence is not None:
                raise ValueError(
                    f"{field_name} cannot have evidence without a value"
                )

        return self


class SupplierComparisonEntry(BaseModel):
    supplier_id: uuid.UUID
    facts: SupplierFacts


class SupplierComparison(BaseModel):
    procurement_event_id: uuid.UUID
    suppliers: list[SupplierComparisonEntry] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_unique_suppliers(self):
        supplier_ids = [
            entry.supplier_id
            for entry in self.suppliers
        ]

        if len(supplier_ids) != len(set(supplier_ids)):
            raise ValueError(
                "A supplier cannot appear more than once in a comparison"
            )

        return self
