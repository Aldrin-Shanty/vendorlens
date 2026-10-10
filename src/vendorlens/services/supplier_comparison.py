import uuid

from pydantic import BaseModel, Field, model_validator

from vendorlens.services.retrieval import SearchResult


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
                raise ValueError(
                    f"{field_name} requires evidence"
                )

            if value is None and evidence is not None:
                raise ValueError(
                    f"{field_name} cannot have evidence without a value"
                )

        return self

def validate_supplier_evidence(
    facts: SupplierFacts,
    supplier_id: uuid.UUID,
    results: list[SearchResult],
) -> None:
    evidence_by_id = {
        index: result
        for index, result in enumerate(results, start=1)
    }

    evidence_fields = [
        facts.unit_price_evidence,
        facts.warranty_evidence,
        facts.delivery_evidence,
    ]

    for evidence in evidence_fields:
        if evidence is None:
            continue

        for evidence_id in evidence.evidence_ids:
            result = evidence_by_id.get(evidence_id)

            if result is None:
                raise ValueError(
                    f"Evidence {evidence_id} does not exist"
                )

            if result.supplier_id != supplier_id:
                raise ValueError(
                    f"Evidence {evidence_id} belongs to another supplier"
                )
