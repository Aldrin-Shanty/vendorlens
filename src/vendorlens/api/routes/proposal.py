import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.api.dependencies import get_db
from vendorlens.api.schemas.proposal import (
    ProposalCreate,
    ProposalRead,
)
from vendorlens.core.security import require_api_key
from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.db.models.proposal import Proposal
from vendorlens.db.models.supplier import Supplier
from vendorlens.api.storage_dependencies import get_storage
from vendorlens.api.deletion import perform_deletion
from vendorlens.services.deletion import DeletionImpact, get_deletion_impact
from vendorlens.services.storage import LocalFileStorage
from vendorlens.services.data_locks import lock_records


router = APIRouter(
    prefix="/proposals",
    tags=["proposals"],
    dependencies=[Depends(require_api_key)],
)


@router.post("", response_model=ProposalRead, status_code=201)
def create_proposal(
    proposal_data: ProposalCreate,
    db: Session = Depends(get_db),
):
    supplier_statement = select(Supplier).where(
        Supplier.id == proposal_data.supplier_id
    )
    supplier = db.scalars(supplier_statement).first()

    if supplier is None:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found",
        )

    procurement_event_statement = select(ProcurementEvent).where(
        ProcurementEvent.id == proposal_data.procurement_event_id
    )
    procurement_event = db.scalars(
        procurement_event_statement
    ).first()

    if procurement_event is None:
        raise HTTPException(
            status_code=404,
            detail="Procurement event not found",
        )

    existing_proposal_statement = select(Proposal).where(
        Proposal.supplier_id == proposal_data.supplier_id,
        Proposal.procurement_event_id
        == proposal_data.procurement_event_id,
    )

    existing_proposal = db.scalars(
        existing_proposal_statement
    ).first()

    if existing_proposal is not None:
        raise HTTPException(
            status_code=409,
            detail="Supplier already has a proposal for this procurement event",
        )

    proposal = Proposal(
        supplier_id=proposal_data.supplier_id,
        procurement_event_id=proposal_data.procurement_event_id,
    )

    db.add(proposal)
    db.commit()
    db.refresh(proposal)

    return proposal


@router.get("", response_model=list[ProposalRead])
def get_proposals(
    db: Session = Depends(get_db),
):
    statement = select(Proposal)
    proposals = db.scalars(statement).all()

    return proposals


@router.get("/{proposal_id}", response_model=ProposalRead)
def get_proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    statement = select(Proposal).where(
        Proposal.id == proposal_id
    )
    proposal = db.scalars(statement).first()

    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail="Proposal not found",
        )

    return proposal

@router.delete("/{proposal_id}", status_code=204)
def delete_proposal(
    proposal_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: LocalFileStorage = Depends(get_storage),
    confirm_related: bool = False,
):
    initial = db.get(Proposal, proposal_id)
    if initial is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    lock_records(db, [f"event:{initial.procurement_event_id}"], shared=False)
    statement = select(Proposal).where(
        Proposal.id == proposal_id
    ).with_for_update()
    proposal = db.scalars(statement).first()

    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail="Proposal not found",
        )

    perform_deletion(db, proposal, storage, confirm_related)


@router.get("/{proposal_id}/deletion-impact", response_model=DeletionImpact)
def preview_proposal_deletion(proposal_id: uuid.UUID, db: Session = Depends(get_db)):
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return get_deletion_impact(db, proposal)
