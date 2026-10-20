"""Human-readable identities and lifecycle operations for saved comparisons."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from vendorlens.db.models.comparison_workflow import ComparisonWorkflowCounter, ComparisonWorkflowRecord
from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.db.models.supplier import Supplier
from vendorlens.services.data_locks import lock_records
from vendorlens.services.errors import DeletionConfirmationRequired, WorkflowNotFoundError
from vendorlens.workflows.numbering import renumber_workflows, delete_workflow_records
from vendorlens.workflows.checkpoint import delete_comparison_threads
from vendorlens.workflows.state import ComparisonWorkflowState, WorkflowStatus


class WorkflowSummary(BaseModel):
    workflow_id: uuid.UUID
    procurement_event_id: uuid.UUID
    supplier_ids: list[uuid.UUID]
    name: str
    sequence_number: int
    created_at: datetime
    status: WorkflowStatus


def saved_states(checkpointer: BaseCheckpointSaver, event_id: uuid.UUID | None = None) -> dict[uuid.UUID, tuple[ComparisonWorkflowState, datetime]]:
    latest: dict[uuid.UUID, tuple[ComparisonWorkflowState, datetime]] = {}
    for item in checkpointer.list(None):
        config = item.config.get("configurable", {})
        if config.get("checkpoint_ns", ""):
            continue
        try:
            workflow_id = uuid.UUID(str(config.get("thread_id")))
        except ValueError:
            continue
        state = item.checkpoint["channel_values"]
        if not {"procurement_event_id", "supplier_ids", "budget"}.issubset(state):
            continue
        if event_id is not None and str(state["procurement_event_id"]) != str(event_id):
            continue
        timestamp = datetime.fromisoformat(item.checkpoint["ts"])
        if workflow_id not in latest:
            latest[workflow_id] = (cast(ComparisonWorkflowState, state), timestamp)
        elif timestamp < latest[workflow_id][1]:
            latest[workflow_id] = (latest[workflow_id][0], timestamp)
    return latest


def register_workflow(db: Session, workflow_id: uuid.UUID, event_id: uuid.UUID, supplier_ids: list[uuid.UUID], created_at: datetime | None = None) -> ComparisonWorkflowRecord:
    existing = db.get(ComparisonWorkflowRecord, workflow_id)
    if existing is not None:
        return existing
    event = db.get(ProcurementEvent, event_id)
    if event is None:
        raise WorkflowNotFoundError("Procurement event not found")
    ids = sorted({str(value) for value in supplier_ids})
    key = hashlib.sha256(",".join(ids).encode()).hexdigest()
    statement = insert(ComparisonWorkflowCounter).values(procurement_event_id=event_id, supplier_key=key, last_number=1)
    statement = statement.on_conflict_do_update(
        index_elements=[ComparisonWorkflowCounter.procurement_event_id, ComparisonWorkflowCounter.supplier_key],
        set_={"last_number": ComparisonWorkflowCounter.last_number + 1},
    ).returning(ComparisonWorkflowCounter.last_number)
    number = db.execute(statement).scalar_one()
    suppliers = db.scalars(select(Supplier).where(Supplier.id.in_([uuid.UUID(value) for value in ids]))).all()
    names = {str(supplier.id): supplier.name for supplier in suppliers}
    labels = sorted([names.get(value, f"Unknown supplier {value[:8]}") for value in ids], key=str.casefold)
    record = ComparisonWorkflowRecord(
        id=workflow_id, procurement_event_id=event_id, supplier_key=key, supplier_ids=ids,
        sequence_number=number, name=f"{event.title} — {' + '.join(labels)} ({number})",
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    return record


def synchronize_catalog(db: Session, checkpointer: BaseCheckpointSaver, event_id: uuid.UUID | None = None) -> tuple[dict[uuid.UUID, tuple[ComparisonWorkflowState, datetime]], dict[uuid.UUID, ComparisonWorkflowRecord]]:
    """Name legacy runs once, oldest first, without modifying graph checkpoints."""
    lock_records(db, ["workflow-names"], shared=False)
    states = saved_states(checkpointer, event_id)
    records: dict[uuid.UUID, ComparisonWorkflowRecord] = {}
    for workflow_id, (state, created_at) in sorted(states.items(), key=lambda item: (item[1][1], str(item[0]))):
        if db.get(ProcurementEvent, state["procurement_event_id"]) is None:
            continue
        records[workflow_id] = register_workflow(db, workflow_id, state["procurement_event_id"], state["supplier_ids"], created_at)
    return states, records


def prepare_workflow(db: Session, checkpointer: BaseCheckpointSaver, event_id: uuid.UUID, supplier_ids: list[uuid.UUID]) -> ComparisonWorkflowRecord:
    synchronize_catalog(db, checkpointer, event_id)
    supplier_key = hashlib.sha256(",".join(sorted({str(value) for value in supplier_ids})).encode()).hexdigest()
    renumber_workflows(db, event_id, supplier_key)
    record = register_workflow(db, uuid.uuid4(), event_id, supplier_ids)
    db.commit()
    return record


def list_workflows(db: Session, checkpointer: BaseCheckpointSaver, event_id: uuid.UUID | None = None) -> list[WorkflowSummary]:
    states, records = synchronize_catalog(db, checkpointer, event_id)
    result = [WorkflowSummary(
        workflow_id=workflow_id, procurement_event_id=record.procurement_event_id,
        supplier_ids=[uuid.UUID(value) for value in record.supplier_ids], name=record.name,
        sequence_number=record.sequence_number, created_at=record.created_at,
        status=states[workflow_id][0].get("status", "running"),
    ) for workflow_id, record in records.items()]
    db.commit()
    return sorted(result, key=lambda item: (item.created_at, str(item.workflow_id)), reverse=True)


def delete_workflows(db: Session, checkpointer: BaseCheckpointSaver, *, event_id: uuid.UUID | None = None, workflow_id: uuid.UUID | None = None, confirmed: bool) -> None:
    lock_records(db, ["workflow-catalog"], shared=workflow_id is not None)
    if workflow_id is not None:
        lock_records(db, [f"workflow:{workflow_id}"], shared=False)
    lock_records(db, ["workflow-names"], shared=False)
    states = saved_states(checkpointer, event_id)
    ids = [workflow_id] if workflow_id is not None and workflow_id in states else list(states) if workflow_id is None else []
    if workflow_id is not None and not ids:
        raise WorkflowNotFoundError("Comparison workflow not found")
    if ids and not confirmed:
        raise DeletionConfirmationRequired("Confirm deletion of saved comparisons and their review decisions. Source proposals and PDFs are kept.")
    if isinstance(checkpointer, PostgresSaver):
        delete_comparison_threads(db, [str(value) for value in ids])
    else:
        for value in ids:
            checkpointer.delete_thread(str(value))
        delete_workflow_records(db, ids)
    db.commit()
