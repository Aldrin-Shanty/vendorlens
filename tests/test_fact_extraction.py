import uuid

import pytest

from vendorlens.services import fact_extraction
from vendorlens.services.retrieval import SearchResult
from vendorlens.services.supplier_comparison import (
    FactEvidence,
    SupplierFacts,
)


def make_search_result(
    supplier_id: uuid.UUID,
    supplier_name: str,
    text: str,
) -> SearchResult:
    return SearchResult(
        chunk_id=uuid.uuid4(),
        supplier_id=supplier_id,
        supplier_name=supplier_name,
        document_version_id=uuid.uuid4(),
        filename=f"{supplier_name.lower()}.pdf",
        page_number=1,
        text=text,
        distance=0.1,
    )


def test_extract_facts_for_supplier(monkeypatch):
    dell_id = uuid.uuid4()
    hp_id = uuid.uuid4()
    event_id = uuid.uuid4()

    results = [
        make_search_result(
            dell_id,
            "Dell",
            "The unit price is 1200 USD. Warranty is 3 years.",
        ),
        make_search_result(
            hp_id,
            "HP",
            "The unit price is 1100 USD. Warranty is 2 years.",
        ),
    ]

    def fake_semantic_search(
        db,
        procurement_event_id,
        query,
        limit,
    ):
        assert procurement_event_id == event_id
        assert limit == 20
        return results

    def fake_extract_supplier_facts(prompt: str):
        assert "1200 USD" in prompt
        assert "1100 USD" not in prompt
        assert "[Evidence 1]" in prompt

        return SupplierFacts(
            supplier_name="Dell",
            unit_price=1200,
            currency="USD",
            unit_price_evidence=FactEvidence(evidence_ids=[1]),
            warranty_years=3,
            warranty_evidence=FactEvidence(evidence_ids=[1]),
            missing_information=["Delivery timeline"],
        )

    monkeypatch.setattr(
        fact_extraction,
        "semantic_search",
        fake_semantic_search,
    )

    monkeypatch.setattr(
        fact_extraction,
        "extract_supplier_facts",
        fake_extract_supplier_facts,
    )

    facts = fact_extraction.extract_facts_for_supplier(
        db=None,
        procurement_event_id=event_id,
        supplier_id=dell_id,
        supplier_name="Dell",
    )

    assert facts.supplier_name == "Dell"
    assert facts.unit_price == 1200
    assert facts.currency == "USD"
    assert facts.warranty_years == 3
    assert facts.delivery_days is None
    assert facts.unit_price_evidence.evidence_ids == [1]


def test_extract_facts_rejects_invalid_evidence(monkeypatch):
    dell_id = uuid.uuid4()

    results = [
        make_search_result(
            dell_id,
            "Dell",
            "The warranty is 3 years.",
        ),
    ]

    monkeypatch.setattr(
        fact_extraction,
        "semantic_search",
        lambda **kwargs: results,
    )

    monkeypatch.setattr(
        fact_extraction,
        "extract_supplier_facts",
        lambda prompt: SupplierFacts(
            supplier_name="Dell",
            warranty_years=3,
            warranty_evidence=FactEvidence(evidence_ids=[99]),
        ),
    )

    with pytest.raises(ValueError, match="does not exist"):
        fact_extraction.extract_facts_for_supplier(
            db=None,
            procurement_event_id=uuid.uuid4(),
            supplier_id=dell_id,
            supplier_name="Dell",
        )
