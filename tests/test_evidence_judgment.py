import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import torch

from vendorlens.services import evidence_judgment, nli
from vendorlens.services.errors import AIOutputError, AIServiceUnavailableError, EvidenceValidationError
from vendorlens.services.schemas.supplier_comparison import EvidenceReference, FactEvidence, SupplierFacts, Relation
from vendorlens.workflows.budget import BudgetExceededError, ExecutionBudget

@pytest.fixture
def runtime(monkeypatch):
    tokenizer = Mock(return_value={"input_ids": torch.ones((1, 20), dtype=torch.long)})
    model = Mock(return_value=SimpleNamespace(logits=torch.tensor([[4.0, 0.0, -1.0]])))
    model.config = SimpleNamespace(id2label={0: "entailment", 1: "neutral", 2: "contradiction"})
    monkeypatch.setattr(nli, "_runtime", (tokenizer, model))
    return tokenizer, model


def test_nli_pairs_and_label_mapping(runtime):
    tokenizer, model = runtime
    result = nli.judge_claims({"warranty_years": {"claim": "The warranty is 3 years.", "evidence": [{"text": "Warranty: 3 years"}]}})
    tokenizer.assert_called_once_with("Warranty: 3 years", "The warranty is 3 years.", truncation=False, return_tensors="pt")
    assert result.answers["warranty_years"].choice == "supports"
    assert sum(result.answers["warranty_years"].probabilities.values()) == pytest.approx(1)
    assert result.input_tokens == 20
    assert model.call_count == 1


@pytest.mark.parametrize("claims", [{}, {str(i): {} for i in range(4)}, {"a": {"text": "x" * 48001}}])
def test_state_budget_rejected_before_loading(monkeypatch, claims):
    monkeypatch.setattr(nli, "load_runtime", lambda: pytest.fail("Unexpected model load"))
    with pytest.raises(AIOutputError):
        nli.judge_claims(claims)


def test_long_pair_rejected_without_truncation(runtime):
    tokenizer, model = runtime
    tokenizer.return_value = {"input_ids": torch.ones((1, 513), dtype=torch.long)}
    with pytest.raises(AIOutputError, match="512-token"):
        nli.judge_claims({"warranty_years": {"claim": "3 years", "evidence": [{"text": "long"}]}})
    model.assert_not_called()


def test_unavailable_model(monkeypatch):
    monkeypatch.setattr(nli, "_runtime", None)
    def fail_load():
        raise OSError("Not cached")
    monkeypatch.setattr(nli, "load_runtime", fail_load)
    with pytest.raises(AIServiceUnavailableError):
        nli.judge_claims({"warranty_years": {"claim": "3 years", "evidence": []}})


@pytest.mark.parametrize("scores, expected", [([4., 0., -1.], "supports"), ([0., 4., -1.], "insufficient"), ([0., -1., 4.], "contradicts")])
def test_all_nli_labels(runtime, scores, expected):
    _, model = runtime
    model.return_value.logits = torch.tensor([scores])
    result = nli.judge_claims({"warranty_years": {"claim": "3 years", "evidence": []}})
    assert result.answers["warranty_years"].choice == expected


@pytest.mark.parametrize("choice, confidence", [("supports", .9), ("supports", .5), ("contradicts", .9), ("insufficient", .9)])
def test_judgment_preserves_cited_sources_and_scores(monkeypatch, choice: Relation, confidence: float):
    monkeypatch.setenv("NLI_EVIDENCE_JUDGMENT_ENABLED", "true")
    facts = SupplierFacts(supplier_name="Dell", warranty_years=3, warranty_evidence=FactEvidence(evidence_ids=[2]))
    evidence = {i: EvidenceReference(chunk_id=uuid.uuid4(), document_version_id=uuid.uuid4(), filename="proposal.pdf", page_number=1, text=text) for i, text in [(1, "Uncited"), (2, "Warranty: 3 years")]}
    def fake_judge(claims):
        assert claims["warranty_years"]["evidence"] == [{"id": 2, "text": "Warranty: 3 years"}]
        assert claims["warranty_years"]["claim"] == "The warranty is 3 years."
        return nli.NLIResult(answers={"warranty_years": nli.NLIAnswer(choice=choice, confidence=confidence, probabilities={choice: confidence})}, input_tokens=20)
    monkeypatch.setattr(evidence_judgment, "judge_claims", fake_judge)
    result = evidence_judgment.judge_supplier_facts(facts, evidence)
    assert result.status == "checked"
    assert result.facts["warranty_years"].relation == choice
    assert result.facts["warranty_years"].confidence == confidence
    assert "requires_review" not in result.model_dump()["facts"]["warranty_years"]
    assert result.revision == nli.REVISION
    assert result.output_tokens == 0
    assert facts.warranty_years == 3


@pytest.mark.parametrize(
    "price, warranty, delivery, price_text, warranty_text",
    [
        (1200.0, 3.0, 14, "1200", "3"),
        (1050.0, 1.0, 7, "1050", "1"),
        (0.0, 0.0, 0, "0", "0"),
        (1199.95, 2.5, 21, "1199.95", "2.5"),
        (1234.56789123, 1.23456789, 30, "1234.56789123", "1.23456789"),
    ],
)
def test_numeric_claims_normalize_whole_values_without_rounding_or_mutating_facts(
    monkeypatch, price, warranty, delivery, price_text, warranty_text
):
    monkeypatch.setenv("NLI_EVIDENCE_JUDGMENT_ENABLED", "true")
    facts = SupplierFacts(
        supplier_name="Synthetic supplier",
        unit_price=price,
        currency="USD",
        unit_price_evidence=FactEvidence(evidence_ids=[1]),
        warranty_years=warranty,
        warranty_evidence=FactEvidence(evidence_ids=[1]),
        delivery_days=delivery,
        delivery_evidence=FactEvidence(evidence_ids=[1]),
    )
    before = facts.model_dump()
    source = EvidenceReference(
        chunk_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        filename="synthetic.pdf",
        page_number=1,
        text=(
            f"The unit price is {price_text} USD. "
            f"The warranty is {warranty_text} years. "
            f"Delivery takes {delivery} days."
        ),
    )
    judge = Mock(return_value=nli.NLIResult(answers={}, input_tokens=0))
    monkeypatch.setattr(evidence_judgment, "judge_claims", judge)

    evidence_judgment.judge_supplier_facts(facts, {1: source})

    judge.assert_called_once()
    claims = judge.call_args.args[0]
    assert {name: claim["claim"] for name, claim in claims.items()} == {
        "unit_price": f"The unit price is {price_text} USD.",
        "warranty_years": f"The warranty is {warranty_text} years.",
        "delivery_days": f"Delivery takes {delivery} days.",
    }
    for claim in claims.values():
        assert claim["evidence"] == [{"id": 1, "text": source.text}]
    assert facts.model_dump() == before


@pytest.mark.parametrize("enabled", ["false", "true"])
def test_empty_facts_make_no_calls(monkeypatch, enabled):
    monkeypatch.setenv("NLI_EVIDENCE_JUDGMENT_ENABLED", enabled)
    monkeypatch.setattr(evidence_judgment, "judge_claims", lambda *args: pytest.fail("Unexpected model call"))
    assert evidence_judgment.judge_supplier_facts(SupplierFacts(supplier_name="Dell"), {}).status == "not_checked"


def test_missing_source_rejected(monkeypatch):
    monkeypatch.setenv("NLI_EVIDENCE_JUDGMENT_ENABLED", "true")
    facts = SupplierFacts(supplier_name="Dell", warranty_years=3, warranty_evidence=FactEvidence(evidence_ids=[99]))
    with pytest.raises(EvidenceValidationError):
        evidence_judgment.judge_supplier_facts(facts, {})

def test_reservation_runs_before_model_execution(runtime):
    _, model = runtime

    def reserve():
        model.assert_not_called()

    reservation = Mock(side_effect=reserve)

    nli.judge_claims(
        {
            "warranty_years": {
                "claim": "The warranty is 3 years.",
                "evidence": [{"text": "Warranty: 3 years."}],
            }
        },
        before_model_call=reservation,
    )

    reservation.assert_called_once_with()
    model.assert_called_once()

@pytest.mark.parametrize("limit", [0, 2])
def test_model_budget_blocks_additional_nli_execution(runtime, limit):
    _, model = runtime
    budget = ExecutionBudget(max_model_calls=limit)

    def reserve():
        nonlocal budget
        budget = budget.reserve_model_call()

    claims = {
        name: {
            "claim": "The warranty is 3 years.",
            "evidence": [{"text": "Warranty: 3 years."}],
        }
        for name in ("first", "second", "third")
    }

    with pytest.raises(BudgetExceededError):
        nli.judge_claims(
            claims,
            before_model_call=reserve,
        )

    assert model.call_count == limit
    assert budget.model_calls_used == limit

def test_oversized_pair_does_not_reserve_model_call(runtime):
    tokenizer, model = runtime

    tokenizer.return_value = {
        "input_ids": torch.ones(
            (1, 513),
            dtype=torch.long,
        )
    }

    reservation = Mock()

    with pytest.raises(AIOutputError, match="512-token"):
        nli.judge_claims(
            {
                "warranty_years": {
                    "claim": "The warranty is 3 years.",
                    "evidence": [{"text": "Long evidence."}],
                }
            },
            before_model_call=reservation,
        )

    reservation.assert_not_called()
    model.assert_not_called()

def test_supplier_judgment_forwards_model_reservation(monkeypatch, runtime):
    monkeypatch.setenv("NLI_EVIDENCE_JUDGMENT_ENABLED", "true")

    facts = SupplierFacts(
        supplier_name="Dell",
        warranty_years=3,
        warranty_evidence=FactEvidence(evidence_ids=[1]),
    )

    evidence = {
        1: EvidenceReference(
            chunk_id=uuid.uuid4(),
            document_version_id=uuid.uuid4(),
            filename="dell.pdf",
            page_number=1,
            text="Warranty: 3 years.",
        )
    }

    reservation = Mock()

    result = evidence_judgment.judge_supplier_facts(
        facts,
        evidence,
        before_model_call=reservation,
    )

    assert result.status == "checked"
    reservation.assert_called_once_with()
