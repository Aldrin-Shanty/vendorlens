import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import torch

from vendorlens.services import evidence_judgment, nli
from vendorlens.services.errors import AIOutputError, AIServiceUnavailableError, EvidenceValidationError
from vendorlens.services.schemas.supplier_comparison import EvidenceReference, FactEvidence, SupplierFacts


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


@pytest.mark.parametrize("choice, confidence, review", [("supports", .9, False), ("supports", .5, True), ("contradicts", .9, True), ("insufficient", .9, True)])
def test_judgment_cited_sources_and_review(monkeypatch, choice, confidence, review):
    monkeypatch.setenv("NLI_EVIDENCE_JUDGMENT_ENABLED", "true")
    facts = SupplierFacts(supplier_name="Dell", warranty_years=3, warranty_evidence=FactEvidence(evidence_ids=[2]))
    evidence = {i: EvidenceReference(chunk_id=uuid.uuid4(), document_version_id=uuid.uuid4(), filename="proposal.pdf", page_number=1, text=text) for i, text in [(1, "Uncited"), (2, "Warranty: 3 years")]}
    def fake_judge(claims):
        assert claims["warranty_years"]["evidence"] == [{"id": 2, "text": "Warranty: 3 years"}]
        assert claims["warranty_years"]["claim"] == "The warranty is 3.0 years."
        return nli.NLIResult(answers={"warranty_years": nli.NLIAnswer(choice=choice, confidence=confidence, probabilities={choice: confidence})}, input_tokens=20)
    monkeypatch.setattr(evidence_judgment, "judge_claims", fake_judge)
    result = evidence_judgment.judge_supplier_facts(facts, evidence)
    assert result.status == "checked"
    assert result.facts["warranty_years"].requires_review is review
    assert result.revision == nli.REVISION
    assert result.output_tokens == 0
    assert facts.warranty_years == 3


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
