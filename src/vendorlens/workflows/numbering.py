"""Keep display numbers consecutive within each event and supplier set."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.db.models.comparison_workflow import ComparisonWorkflowCounter, ComparisonWorkflowRecord
from vendorlens.services.data_locks import lock_records


def renumber_workflows(db: Session) -> None:
    lock_records(db, ["workflow-names"], shared=False)
    counters = db.scalars(select(ComparisonWorkflowCounter)).all()
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
