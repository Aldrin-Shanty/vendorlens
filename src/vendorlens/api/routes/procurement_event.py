import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.api.dependencies import get_db
from vendorlens.api.schemas.procurement_event import (
    ProcurementEventCreate,
    ProcurementEventRead,
    ProcurementEventUpdate,
)
from vendorlens.core.security import require_api_key
from vendorlens.db.models.procurement_event import ProcurementEvent


router = APIRouter(
    prefix="/procurement-events",
    tags=["procurement-events"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=ProcurementEventRead, status_code=201)
def create_procurement_event(
    procurement_event_data: ProcurementEventCreate,
    db: Session = Depends(get_db),
):
    procurement_event = ProcurementEvent(
        title=procurement_event_data.title,
    )

    db.add(procurement_event)
    db.commit()
    db.refresh(procurement_event)

    return procurement_event


@router.get("", response_model=list[ProcurementEventRead])
def get_procurement_events(
    db: Session = Depends(get_db),
):
    statement = select(ProcurementEvent)
    procurement_events = db.scalars(statement).all()

    return procurement_events


@router.get("/{procurement_event_id}", response_model=ProcurementEventRead)
def get_procurement_event(
    procurement_event_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    statement = select(ProcurementEvent).where(
        ProcurementEvent.id == procurement_event_id
    )
    procurement_event = db.scalars(statement).first()

    if procurement_event is None:
        raise HTTPException(
            status_code=404,
            detail="Procurement event not found",
        )

    return procurement_event


@router.put("/{procurement_event_id}", response_model=ProcurementEventRead)
def update_procurement_event(
    procurement_event_id: uuid.UUID,
    procurement_event_data: ProcurementEventUpdate,
    db: Session = Depends(get_db),
):
    statement = select(ProcurementEvent).where(
        ProcurementEvent.id == procurement_event_id
    )
    procurement_event = db.scalars(statement).first()

    if procurement_event is None:
        raise HTTPException(
            status_code=404,
            detail="Procurement event not found",
        )

    procurement_event.title = procurement_event_data.title

    db.commit()
    db.refresh(procurement_event)

    return procurement_event


@router.delete("/{procurement_event_id}", status_code=204)
def delete_procurement_event(
    procurement_event_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    statement = select(ProcurementEvent).where(
        ProcurementEvent.id == procurement_event_id
    )
    procurement_event = db.scalars(statement).first()

    if procurement_event is None:
        raise HTTPException(
            status_code=404,
            detail="Procurement event not found",
        )

    db.delete(procurement_event)
    db.commit()
