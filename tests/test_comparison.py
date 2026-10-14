import uuid
from unittest.mock import Mock

from sqlalchemy.orm import Session

import pytest

from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.db.models.proposal import Proposal
from vendorlens.db.models.supplier import Supplier
from vendorlens.services import comparison
from vendorlens.services.errors import SupplierSelectionError
from vendorlens.services.fact_extraction import SupplierExtractionResult
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

    def fake_extract(**kwargs):
        assert kwargs["db"] is db
        assert kwargs["procurement_event_id"] == event.id
        calls.append(kwargs["supplier_id"])
        return SupplierExtractionResult(
            facts=SupplierFacts(
                supplier_name=kwargs["supplier_name"], warranty_years=3,
                warranty_evidence=FactEvidence(evidence_ids=[2]),
            ),
            evidence={2: reference},
        )

    monkeypatch.setattr(comparison, "extract_facts_for_supplier", fake_extract)
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

    def unexpected_extraction(**kwargs):
        pytest.fail("An invalid selection must not trigger AI extraction")

    monkeypatch.setattr(comparison, "extract_facts_for_supplier", unexpected_extraction)
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
