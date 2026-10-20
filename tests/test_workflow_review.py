import uuid

import pytest

from vendorlens.services.schemas.supplier_comparison import (
    EvidenceJudgment,
    FactEvidence,
    FactJudgment,
    SupplierComparison,
    SupplierComparisonEntry,
    SupplierFacts,
)
from vendorlens.workflows.review import (
    FactField,
    collect_review_issues,
)


@pytest.fixture
def comparison():
    entries = []

    for name in ("Dell", "HP"):
        facts = SupplierFacts(
            supplier_name=name,
            unit_price=1200,
            currency="USD",
            unit_price_evidence=FactEvidence(evidence_ids=[1]),
            warranty_years=3,
            warranty_evidence=FactEvidence(evidence_ids=[1]),
            delivery_days=14,
            delivery_evidence=FactEvidence(evidence_ids=[1]),
        )

        fields: tuple[FactField, ...] = (
            "unit_price",
            "warranty_years",
            "delivery_days",
        )

        judgments = {
            field: FactJudgment(
                relation="supports",
                confidence=0.95,
                probabilities={
                    "supports": 0.95,
                    "contradicts": 0.02,
                    "insufficient": 0.03,
                },
            )
            for field in fields
        }

        entries.append(
            SupplierComparisonEntry(
                supplier_id=uuid.uuid4(),
                facts=facts,
                judgment=EvidenceJudgment(
                    status="checked",
                    model="test-model",
                    facts=judgments,
                ),
            )
        )

    return SupplierComparison(
        procurement_event_id=uuid.uuid4(),
        suppliers=entries,
    )


def test_supported_complete_comparison_needs_no_review(comparison):
    assert collect_review_issues(comparison) == []


def test_missing_value_requires_review(comparison):
    entry = comparison.suppliers[0]

    entry.facts = entry.facts.model_copy(
        update={
            "delivery_days": None,
            "delivery_evidence": None,
        }
    )

    issues = collect_review_issues(comparison)

    assert len(issues) == 1
    assert issues[0].supplier_id == entry.supplier_id
    assert issues[0].field == "delivery_days"
    assert issues[0].reason == "missing_value"


@pytest.mark.parametrize(
    "relation, confidence, expected",
    [
        ("contradicts", 0.95, "contradicted"),
        ("insufficient", 0.95, "insufficient"),
        ("supports", 0.60, "low_confidence"),
    ],
)
def test_judgment_issues_require_review(
    comparison, relation, confidence, expected
):
    entry = comparison.suppliers[0]

    entry.judgment.facts["warranty_years"] = (
        FactJudgment.model_validate(
            {
                "relation": relation,
                "confidence": confidence,
                "probabilities": {relation: 1.0},
            }
        )
    )

    issues = collect_review_issues(comparison)

    assert len(issues) == 1
    assert issues[0].field == "warranty_years"
    assert issues[0].reason == expected


def test_missing_field_judgment_requires_review(comparison):
    del comparison.suppliers[0].judgment.facts["warranty_years"]

    issues = collect_review_issues(comparison)

    assert len(issues) == 1
    assert issues[0].reason == "not_checked"


def test_disabled_judgment_does_not_imply_support(comparison):
    comparison.suppliers[0].judgment = EvidenceJudgment()

    issues = collect_review_issues(comparison)

    assert len(issues) == 3
    assert all(issue.reason == "not_checked" for issue in issues)


def test_assessment_preserves_comparison(comparison):
    from vendorlens.workflows.comparison import assess_review
    from vendorlens.workflows.state import create_initial_state

    before = comparison.model_dump()
    state = create_initial_state(
        comparison.procurement_event_id,
        [entry.supplier_id for entry in comparison.suppliers],
    )
    state["comparison"] = comparison

    command = assess_review(state)

    assert command.update == {"status": "completed", "review_issues": []}
    assert command.goto == "__end__"
    assert comparison.model_dump() == before


def test_assessment_routes_issues_to_human_review(comparison):
    from vendorlens.workflows.comparison import assess_review
    from vendorlens.workflows.state import create_initial_state

    comparison.suppliers[0].judgment = EvidenceJudgment()
    before = comparison.model_dump()
    state = create_initial_state(
        comparison.procurement_event_id,
        [entry.supplier_id for entry in comparison.suppliers],
    )
    state["comparison"] = comparison
    command = assess_review(state)
    assert command.goto == "human_review"
    update = command.update
    assert isinstance(update, dict)
    assert update["status"] == "awaiting_review"
    assert len(update["review_issues"]) == 3
    assert comparison.model_dump() == before
