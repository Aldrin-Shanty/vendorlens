import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from vendorlens.api.dependencies import get_db
from vendorlens.core.security import require_api_key
from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.api.schemas.search import SearchRequest, SearchResultRead
from vendorlens.services.retrieval import semantic_search


router = APIRouter(
    prefix="/procurement-events",
    tags=["search"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "/{procurement_event_id}/search",
    response_model=list[SearchResultRead],
)
def search_procurement_event(
    procurement_event_id: uuid.UUID,
    request: SearchRequest,
    db: Session = Depends(get_db),
):
    event = db.get(ProcurementEvent, procurement_event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Procurement event not found",
        )

    return semantic_search(
        db=db,
        procurement_event_id=procurement_event_id,
        query=request.query,
        limit=request.limit,
    )
