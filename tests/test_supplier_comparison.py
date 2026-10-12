import uuid

import pytest
from pydantic import ValidationError

from vendorlens.services.retrieval import SearchResult
from vendorlens.services.schemas.supplier_comparison import FactEvidence, SupplierFacts, SupplierComparison, SupplierComparisonEntry
from vendorlens.services.evidence_validation import validate_supplier_evidence


def test_supplier_evidence_rejects_other_supplier():
    dell_id = uuid.uuid4()
    hp_id = uuid.uuid4()

    results = [
        SearchResult(
            chunk_id=uuid.uuid4(),
            supplier_id=dell_id,
            supplier_name="Dell",
            document_version_id=uuid.uuid4(),
            filename="dell.pdf",
            page_number=1,
            text="Laptop warranty is three years.",
            distance=0.1,
        ),
        SearchResult(
            chunk_id=uuid.uuid4(),
            supplier_id=hp_id,
            supplier_name="HP",
            document_version_id=uuid.uuid4(),
            filename="hp.pdf",
            page_number=1,
            text="Laptop warranty is two years.",
            distance=0.2,
        ),
    ]

    dell_facts = SupplierFacts(
        supplier_name="Dell",
        warranty_years=2,
        warranty_evidence=FactEvidence(evidence_ids=[2]),
    )

    with pytest.raises(
        ValueError,
        match="belongs to another supplier",
    ):
        validate_supplier_evidence(
            facts=dell_facts,
            supplier_id=dell_id,
            results=results,
        )

def test_supplier_comparison_requires_unique_suppliers():
    event_id = uuid.uuid4()
    dell_id = uuid.uuid4()

    dell_facts = SupplierFacts(
        supplier_name="Dell",
    )

    with pytest.raises(
        ValidationError,
        match="A supplier cannot appear more than once",
    ):
        SupplierComparison(
            procurement_event_id=event_id,
            suppliers=[
                SupplierComparisonEntry(
                    supplier_id=dell_id,
                    facts=dell_facts,
                ),
                SupplierComparisonEntry(
                    supplier_id=dell_id,
                    facts=dell_facts,
                ),
            ],
        )
