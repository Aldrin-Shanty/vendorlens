import uuid
from typing import Literal, NotRequired, TypedDict

from vendorlens.services.schemas.supplier_comparison import SupplierComparison
from vendorlens.workflows.budget import ExecutionBudget
from vendorlens.workflows.review import ReviewIssue, ReviewDecision

WorkflowStatus = Literal[
    "running",
    "completed",
    "awaiting_review",
    "reviewed",
    "rejected",
    "stopped",
    "failed",
]

class ComparisonWorkflowState(TypedDict):
    procurement_event_id: uuid.UUID
    supplier_ids: list[uuid.UUID]
    budget: ExecutionBudget
    comparison: NotRequired[SupplierComparison | None]
    status: NotRequired[WorkflowStatus]
    error: NotRequired[str | None]
    review_issues: NotRequired[list[ReviewIssue]]
    review_decision: NotRequired[ReviewDecision]

class ComparisonWorkflowUpdate(TypedDict, total=False):
    budget: ExecutionBudget
    comparison: SupplierComparison | None
    status: WorkflowStatus
    error: str | None
    review_issues: NotRequired[list[ReviewIssue]]
    review_decision: ReviewDecision

def create_initial_state(
    procurement_event_id: uuid.UUID,
    supplier_ids: list[uuid.UUID],
    budget: ExecutionBudget | None = None,
) -> ComparisonWorkflowState:
    """Build starting state from already parsed request values."""
    return {
        "procurement_event_id": procurement_event_id,
        "supplier_ids": list(supplier_ids),
        "budget": budget if budget is not None else ExecutionBudget(),
    }
