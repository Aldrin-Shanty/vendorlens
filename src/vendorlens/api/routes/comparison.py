import uuid

import httpx

from pydantic import ValidationError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from langgraph.checkpoint.base import BaseCheckpointSaver

from vendorlens.workflows.budget import ExecutionBudget
from vendorlens.workflows.services import (
    get_comparison_workflow,
    start_comparison_workflow,
)
from vendorlens.api.dependencies import get_db, get_checkpointer
from vendorlens.api.schemas.comparison import (
    ComparisonWorkflowResponse,
    CompareSuppliersRequest,
)
from vendorlens.core.security import require_api_key
from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.services.comparison import compare_suppliers
from vendorlens.services.schemas.supplier_comparison import SupplierComparison
from vendorlens.services.errors import AIOutputError, AIServiceUnavailableError, EvidenceValidationError, SupplierSelectionError, WorkflowNotFoundError

router = APIRouter(
    prefix="/procurement-events",
    tags=["comparison"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "/{procurement_event_id}/compare",
    response_model=SupplierComparison,
)
def compare_procurement_event(
    procurement_event_id: uuid.UUID,
    request: CompareSuppliersRequest,
    db: Session = Depends(get_db),
):
    event = db.get(ProcurementEvent, procurement_event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Procurement event not found",
        )

    try:
        return compare_suppliers(
            db=db,
            procurement_event_id=procurement_event_id,
            supplier_ids=request.supplier_ids,
        )

    except SupplierSelectionError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except (
        EvidenceValidationError,
        AIOutputError,
        ValidationError,
    ) as exc:
        raise HTTPException(
            status_code=502,
            detail="AI-generated supplier facts could not be validated",
        ) from exc

    except (
        AIServiceUnavailableError,
        httpx.RequestError,
        httpx.HTTPStatusError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail="The AI service is currently unavailable",
        ) from exc

@router.post(
    "/{procurement_event_id}/comparison-workflows",
    response_model=ComparisonWorkflowResponse,
    status_code=201,
)
def start_procurement_comparison_workflow(
    procurement_event_id: uuid.UUID,
    request: CompareSuppliersRequest,
    db: Session = Depends(get_db),
    checkpointer: BaseCheckpointSaver = Depends(get_checkpointer),
):
    event = db.get(ProcurementEvent, procurement_event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Procurement event not found",
        )

    supplier_count = len(request.supplier_ids)

    workflow_id = start_comparison_workflow(
        db,
        checkpointer=checkpointer,
        procurement_event_id=procurement_event_id,
        supplier_ids=request.supplier_ids,
        budget=ExecutionBudget(
            max_model_calls=4 * supplier_count,
            max_tool_calls=supplier_count,
        ),
    )

    state = get_comparison_workflow(
        db,
        checkpointer=checkpointer,
        procurement_event_id=procurement_event_id,
        workflow_id=workflow_id,
    )

    return ComparisonWorkflowResponse.model_validate(
        {
            **state,
            "workflow_id": workflow_id,
        }
    )

@router.get(
    "/{procurement_event_id}/comparison-workflows/{workflow_id}",
    response_model=ComparisonWorkflowResponse,
)

def get_procurement_comparison_workflow(
    procurement_event_id: uuid.UUID,
    workflow_id: uuid.UUID,
    db: Session = Depends(get_db),
    checkpointer: BaseCheckpointSaver = Depends(get_checkpointer),
):
    event = db.get(ProcurementEvent, procurement_event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Procurement event not found",
        )

    try:
        state = get_comparison_workflow(
            db,
            checkpointer=checkpointer,
            procurement_event_id=procurement_event_id,
            workflow_id=workflow_id,
        )

    except WorkflowNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Comparison workflow not found",
        ) from exc

    return ComparisonWorkflowResponse.model_validate(
        {
            **state,
            "workflow_id": workflow_id,
        }
    )
