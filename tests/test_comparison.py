import uuid
from unittest.mock import Mock

from sqlalchemy.orm import Session

import pytest

from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.db.models.proposal import Proposal
from vendorlens.db.models.supplier import Supplier
from vendorlens.services import comparison, fact_extraction
from vendorlens.services.errors import AIOutputError, EvidenceValidationError, SupplierSelectionError
from vendorlens.services.retrieval import SearchResult
from vendorlens.services.schemas.supplier_comparison import (
    EvidenceJudgment, EvidenceReference, FactEvidence, SupplierFacts,
)


def create_selection(db):
    event = ProcurementEvent(title="Laptops")
    suppliers = [Supplier(name="Dell"), Supplier(name="HP")]
    db.add_all([event, *suppliers])
    db.flush()
    db.add_all([
        Proposal(procurement_event_id=event.id, supplier_id=supplier.id)
        for supplier in suppliers
    ])
    db.flush()
    return event, suppliers


def test_comparison_preserves_facts_and_provenance(db, monkeypatch):
    event, suppliers = create_selection(db)
    reference = EvidenceReference(
        chunk_id=uuid.uuid4(), document_version_id=uuid.uuid4(),
        filename="proposal.pdf", page_number=2, text="Warranty: 3 years.",
    )
    calls = []

    def fake_retrieve(db_arg, procurement_event_id, supplier_id):
        assert db_arg is db
        assert procurement_event_id == event.id
        calls.append(supplier_id)
        return [SearchResult(
            chunk_id=reference.chunk_id, supplier_id=supplier_id,
            supplier_name=next(s.name for s in suppliers if s.id == supplier_id),
            document_version_id=reference.document_version_id,
            filename=reference.filename, page_number=reference.page_number,
            text=text, distance=0.1,
        ) for text in ("Uncited background", reference.text)]

    def fake_extract(supplier_name, sources):
        assert sources[1].text == reference.text
        return SupplierFacts(
            supplier_name=supplier_name, warranty_years=3,
            warranty_evidence=FactEvidence(evidence_ids=[2]),
        )

    monkeypatch.setattr(comparison, "retrieve_supplier_evidence", fake_retrieve)
    monkeypatch.setattr(comparison, "extract_facts_from_evidence", fake_extract)
    judgment_calls = []

    def fake_judge(facts, evidence):
        judgment_calls.append(facts.supplier_name)
        assert evidence == {2: reference}
        return EvidenceJudgment(status="checked", model="MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli")

    monkeypatch.setattr(comparison, "judge_supplier_facts", fake_judge)
    supplier_ids = [supplier.id for supplier in reversed(suppliers)]
    result = comparison.compare_suppliers(db, event.id, supplier_ids)

    assert calls == supplier_ids
    assert judgment_calls == ["HP", "Dell"]
    assert [entry.supplier_id for entry in result.suppliers] == supplier_ids
    assert [entry.facts.supplier_name for entry in result.suppliers] == ["HP", "Dell"]
    for entry in result.suppliers:
        assert entry.facts.warranty_evidence is not None
        assert entry.facts.warranty_evidence.evidence_ids == [2]
        assert entry.evidence == {2: reference}
        assert entry.judgment.status == "checked"


def test_comparison_rejects_cross_event_supplier_before_extraction(db, monkeypatch):
    event, suppliers = create_selection(db)
    other_event = ProcurementEvent(title="Other event")
    outsider = Supplier(name="Other supplier")
    db.add_all([other_event, outsider])
    db.flush()
    db.add(Proposal(procurement_event_id=other_event.id, supplier_id=outsider.id))
    db.flush()

    def unexpected_extraction(*args, **kwargs):
        pytest.fail("An invalid selection must not trigger AI extraction")

    monkeypatch.setattr(comparison, "retrieve_supplier_evidence", unexpected_extraction)
    with pytest.raises(SupplierSelectionError, match="no proposal"):
        comparison.compare_suppliers(db, event.id, [suppliers[0].id, outsider.id])


@pytest.mark.parametrize("duplicate", [False, True])
def test_comparison_rejects_invalid_selection(duplicate):
    supplier_id = uuid.uuid4()
    supplier_ids = [supplier_id, supplier_id] if duplicate else [supplier_id]
    with pytest.raises(SupplierSelectionError):
        comparison.compare_suppliers(Mock(spec=Session), uuid.uuid4(), supplier_ids)


def test_comparison_rejects_supplier_budget():
    with pytest.raises(SupplierSelectionError, match="At most eight"):
        comparison.compare_suppliers(Mock(spec=Session), uuid.uuid4(), [uuid.uuid4() for _ in range(9)])


@pytest.mark.parametrize("failure, error", [
    ("no_sources", SupplierSelectionError),
    ("wrong_name", AIOutputError),
    ("invalid_citation", EvidenceValidationError),
    ("wrong_owner", EvidenceValidationError),
])
def test_comparison_stops_before_judgment_on_invalid_extraction(db, monkeypatch, failure, error):
    event, suppliers = create_selection(db)
    source = SearchResult(
        chunk_id=uuid.uuid4(),
        supplier_id=suppliers[1].id if failure == "wrong_owner" else suppliers[0].id,
        supplier_name="Dell", document_version_id=uuid.uuid4(),
        filename="dell.pdf", page_number=1, text="Warranty: 3 years.", distance=0.1,
    )
    monkeypatch.setattr(fact_extraction, "semantic_search", lambda **kwargs: [] if failure == "no_sources" else [source])
    model_calls = []

    def fake_model(prompt):
        model_calls.append(prompt)
        return SupplierFacts(
            supplier_name="HP" if failure == "wrong_name" else "Dell",
            warranty_years=3,
            warranty_evidence=FactEvidence(evidence_ids=[99 if failure == "invalid_citation" else 1]),
        )

    monkeypatch.setattr(fact_extraction, "extract_supplier_facts", fake_model)
    monkeypatch.setattr(comparison, "judge_supplier_facts", lambda *args: pytest.fail("Invalid facts must not reach judgment"))
    with pytest.raises(error):
        comparison.compare_suppliers(db, event.id, [supplier.id for supplier in suppliers])
    assert len(model_calls) == (0 if failure == "no_sources" else 1)
