import uuid

import httpx

from pydantic import ValidationError
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from vendorlens.api.dependencies import get_db
from vendorlens.api.schemas.comparison import CompareSuppliersRequest
from vendorlens.core.security import require_api_key
from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.services.comparison import compare_suppliers
from vendorlens.services.schemas.supplier_comparison import SupplierComparison
from vendorlens.services.errors import AIOutputError, AIServiceUnavailableError, EvidenceValidationError, SupplierSelectionError

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
