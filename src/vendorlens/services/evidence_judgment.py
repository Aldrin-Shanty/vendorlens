import os

from collections.abc import Callable

from vendorlens.services.nli import judge_claims
from vendorlens.services.errors import EvidenceValidationError
from vendorlens.services.schemas.supplier_comparison import (
    EvidenceJudgment, EvidenceReference, FactJudgment, SupplierFacts,
)


def judge_supplier_facts(
    facts: SupplierFacts,
    evidence: dict[int, EvidenceReference],
    *,
    before_model_call: Callable[[], None] | None = None,
) -> EvidenceJudgment:
    """Annotate facts for human review; a model verdict never rewrites source facts."""
    if os.getenv("NLI_EVIDENCE_JUDGMENT_ENABLED", "false").lower() != "true":
        return EvidenceJudgment()

    claims = {}
    for name, value, citations, unit in (
        ("unit_price", facts.unit_price, facts.unit_price_evidence, facts.currency),
        ("warranty_years", facts.warranty_years, facts.warranty_evidence, "years"),
        ("delivery_days", facts.delivery_days, facts.delivery_evidence, "days"),
    ):
        if value is None or citations is None:
            continue
        if any(evidence_id not in evidence for evidence_id in citations.evidence_ids):
            raise EvidenceValidationError(f"Missing source evidence for {name}")
        claims[name] = {
            "claim": {
                "unit_price": f"The unit price is {value} {unit}.",
                "warranty_years": f"The warranty is {value} years.",
                "delivery_days": f"Delivery takes {value} days.",
            }[name],
            "evidence": [
                {"id": evidence_id, "text": evidence[evidence_id].text}
                for evidence_id in citations.evidence_ids
            ],
        }
    if not claims:
        return EvidenceJudgment()

    if before_model_call is None:
        result = judge_claims(claims)
    else:
        result = judge_claims(
            claims,
            before_model_call=before_model_call,
        )

    return EvidenceJudgment(
        status="checked", model=result.model,
        revision=result.revision,
        input_tokens=result.input_tokens, output_tokens=0,
        facts={
            name: FactJudgment(
                relation=answer.choice, confidence=answer.confidence,
                probabilities=answer.probabilities,
            )
            for name, answer in result.answers.items()
        },
    )
