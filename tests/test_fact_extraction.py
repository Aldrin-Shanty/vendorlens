
import uuid
from unittest.mock import Mock

from sqlalchemy.orm import Session

import pytest

from vendorlens.services import fact_extraction
from vendorlens.services.errors import AIOutputError, EvidenceValidationError, SupplierSelectionError
from vendorlens.services.retrieval import SearchResult
from vendorlens.services.schemas.supplier_comparison import (
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

    dell_result = results[0]

    def fake_semantic_search(
        db,
        procurement_event_id,
        query,
        limit,
        supplier_id,
    ):
        assert procurement_event_id == event_id
        assert supplier_id == dell_id
        assert limit == 20

        return [
            result
            for result in results
            if result.supplier_id == supplier_id
        ]

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

    result = fact_extraction.extract_facts_for_supplier(
        db=Mock(spec=Session),
        procurement_event_id=event_id,
        supplier_id=dell_id,
        supplier_name="Dell",
    )

    # Verify extracted facts.
    assert result.facts.supplier_name == "Dell"
    assert result.facts.unit_price == 1200
    assert result.facts.currency == "USD"
    assert result.facts.warranty_years == 3
    assert result.facts.delivery_days is None
    assert result.facts.unit_price_evidence is not None
    assert result.facts.unit_price_evidence.evidence_ids == [1]

    # Verify source provenance.
    assert set(result.evidence.keys()) == {1}

    evidence = result.evidence[1]

    assert evidence.chunk_id == dell_result.chunk_id
    assert evidence.document_version_id == dell_result.document_version_id
    assert evidence.filename == "dell.pdf"
    assert evidence.page_number == 1
    assert evidence.text == dell_result.text


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

    with pytest.raises(
        EvidenceValidationError,
        match="does not exist",
    ):
        fact_extraction.extract_facts_for_supplier(
            db=Mock(spec=Session),
            procurement_event_id=uuid.uuid4(),
            supplier_id=dell_id,
            supplier_name="Dell",
        )


def test_extraction_returns_only_cited_evidence(monkeypatch):
    dell_id = uuid.uuid4()
    event_id = uuid.uuid4()

    cited_result = make_search_result(
        dell_id,
        "Dell",
        "The unit price is 1200 USD.",
    )

    uncited_result = make_search_result(
        dell_id,
        "Dell",
        "General company background information.",
    )

    results = [cited_result, uncited_result]

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
            unit_price=1200,
            currency="USD",
            unit_price_evidence=FactEvidence(evidence_ids=[1]),
            missing_information=[
                "Warranty",
                "Delivery timeline",
            ],
        ),
    )

    result = fact_extraction.extract_facts_for_supplier(
        db=Mock(spec=Session),
        procurement_event_id=event_id,
        supplier_id=dell_id,
        supplier_name="Dell",
    )

    assert result.facts.unit_price == 1200

    # Only Evidence 1 was cited.
    assert set(result.evidence.keys()) == {1}

    # The cited chunk is present.
    assert result.evidence[1].chunk_id == cited_result.chunk_id

    # The uncited chunk must not appear.
    assert all(
        evidence.chunk_id != uncited_result.chunk_id
        for evidence in result.evidence.values()
    )


def test_extraction_preserves_original_evidence_ids(monkeypatch):
    dell_id = uuid.uuid4()

    results = [
        make_search_result(
            dell_id,
            "Dell",
            "General background information.",
        ),
        make_search_result(
            dell_id,
            "Dell",
            "Warranty: 3 years.",
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
            warranty_evidence=FactEvidence(evidence_ids=[2]),
        ),
    )

    result = fact_extraction.extract_facts_for_supplier(
        db=Mock(spec=Session),
        procurement_event_id=uuid.uuid4(),
        supplier_id=dell_id,
        supplier_name="Dell",
    )

    # Evidence 2 remains Evidence 2 after filtering.
    assert set(result.evidence.keys()) == {2}
    assert result.evidence[2].chunk_id == results[1].chunk_id
    assert result.facts.warranty_evidence is not None
    assert result.facts.warranty_evidence.evidence_ids == [2]


def test_extraction_rejects_missing_evidence_without_ai_call(monkeypatch):
    monkeypatch.setattr(fact_extraction, "semantic_search", lambda **kwargs: [])

    def unexpected_extraction(prompt):
        pytest.fail("No evidence must not trigger an AI call")

    monkeypatch.setattr(fact_extraction, "extract_supplier_facts", unexpected_extraction)
    with pytest.raises(SupplierSelectionError, match="No proposal evidence"):
        fact_extraction.extract_facts_for_supplier(Mock(spec=Session), uuid.uuid4(), uuid.uuid4(), "Dell")


def test_extraction_rejects_wrong_supplier_name(monkeypatch):
    supplier_id = uuid.uuid4()
    monkeypatch.setattr(fact_extraction, "semantic_search", lambda **kwargs: [
        make_search_result(supplier_id, "Dell", "Warranty: 3 years.")
    ])
    monkeypatch.setattr(fact_extraction, "extract_supplier_facts", lambda prompt: SupplierFacts(
        supplier_name="HP",
    ))
    with pytest.raises(AIOutputError, match="does not match"):
        fact_extraction.extract_facts_for_supplier(Mock(spec=Session), uuid.uuid4(), supplier_id, "Dell")
