import uuid

from pydantic import BaseModel, Field, model_validator

from vendorlens.services.schemas.supplier_comparison import (
    SupplierComparison,
)
from vendorlens.workflows.budget import ExecutionBudget
from vendorlens.workflows.review import ReviewDecision, ReviewIssue
from vendorlens.workflows.state import WorkflowStatus

class CompareSuppliersRequest(BaseModel):
    supplier_ids: list[uuid.UUID] = Field(min_length=2, max_length=8)

    @model_validator(mode="after")
    def validate_unique_suppliers(self):
        if len(self.supplier_ids) != len(set(self.supplier_ids)):
            raise ValueError("Duplicate supplier IDs are not allowed")

        return self

class ComparisonWorkflowResponse(BaseModel):
    workflow_id: uuid.UUID
    procurement_event_id: uuid.UUID
    status: WorkflowStatus
    budget: ExecutionBudget
    comparison: SupplierComparison | None = None
    review_issues: list[ReviewIssue] = Field(default_factory=list)
    review_decision: ReviewDecision | None = None
    error: str | None = None
