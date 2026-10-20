"""Keep display numbers consecutive within each event and supplier set."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from vendorlens.db.models.comparison_workflow import ComparisonWorkflowCounter, ComparisonWorkflowRecord
from vendorlens.services.data_locks import lock_records


def renumber_workflows(db: Session, event_id: uuid.UUID, supplier_key: str) -> None:
    lock_records(db, ["workflow-names"], shared=False)
    counters = db.scalars(select(ComparisonWorkflowCounter).where(
        ComparisonWorkflowCounter.procurement_event_id == event_id,
        ComparisonWorkflowCounter.supplier_key == supplier_key,
    )).all()
    for counter in counters:
        records = db.scalars(
            select(ComparisonWorkflowRecord).where(
                ComparisonWorkflowRecord.procurement_event_id == counter.procurement_event_id,
                ComparisonWorkflowRecord.supplier_key == counter.supplier_key,
            ).order_by(ComparisonWorkflowRecord.sequence_number)
        ).all()
        # Update in ascending order so each lower number is free before reuse.
        for number, record in enumerate(records, 1):
            if record.sequence_number != number:
                record.sequence_number = number
                record.name = f"{record.name.rsplit(' (', 1)[0]} ({number})"
                db.flush()
        counter.last_number = len(records)
    db.flush()


def delete_workflow_records(db: Session, workflow_ids: list[uuid.UUID]) -> None:
    """Delete names and close gaps in affected groups within the same transaction."""
    lock_records(db, ["workflow-names"], shared=False)
    groups = db.execute(select(
        ComparisonWorkflowRecord.procurement_event_id,
        ComparisonWorkflowRecord.supplier_key,
    ).where(ComparisonWorkflowRecord.id.in_(workflow_ids)).distinct()).all()
    db.execute(delete(ComparisonWorkflowRecord).where(ComparisonWorkflowRecord.id.in_(workflow_ids)))
    for event_id, supplier_key in groups:
        renumber_workflows(db, event_id, supplier_key)
