import uuid

from vendorlens.services.retrieval import SearchResult
from vendorlens.services.schemas.supplier_comparison import SupplierFacts


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
