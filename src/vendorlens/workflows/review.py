import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vendorlens.services.schemas.supplier_comparison import SupplierComparison


FactField = Literal["unit_price", "warranty_years", "delivery_days"]

ReviewReason = Literal[
    "missing_value",
    "not_checked",
    "contradicted",
    "insufficient",
    "low_confidence",
]


class ReviewIssue(BaseModel):
    supplier_id: uuid.UUID
    field: FactField
    reason: ReviewReason

class ReviewDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    action: Literal["acknowledge", "reject"]
    comment: str = Field(min_length=1, max_length=1000)

def collect_review_issues(
    comparison: SupplierComparison,
) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []

    fields: tuple[FactField, ...] = (
        "unit_price",
        "warranty_years",
        "delivery_days",
    )

    for entry in comparison.suppliers:
        for field in fields:
            value = getattr(entry.facts, field)
            judgment = entry.judgment.facts.get(field)
            reason: ReviewReason | None = None

            if value is None:
                reason = "missing_value"

            elif entry.judgment.status != "checked" or judgment is None:
                reason = "not_checked"

            elif judgment.relation == "contradicts":
                reason = "contradicted"

            elif judgment.relation == "insufficient":
                reason = "insufficient"

            elif judgment.confidence < 0.8:
                reason = "low_confidence"

            if reason is not None:
                issues.append(
                    ReviewIssue(
                        supplier_id=entry.supplier_id,
                        field=field,
                        reason=reason,
                    )
                )

    return issues
