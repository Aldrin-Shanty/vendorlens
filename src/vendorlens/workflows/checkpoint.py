from collections.abc import Generator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy.engine import make_url
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session
from psycopg import Connection
from psycopg.rows import DictRow
from typing import cast
import uuid
from vendorlens.db.models.comparison_workflow import ComparisonWorkflowRecord
from vendorlens.workflows.numbering import renumber_workflows
from vendorlens.services.data_locks import lock_records


@contextmanager
def open_checkpointer(
    database_url: str,
) -> Generator[PostgresSaver, None, None]:
    """Open a PostgreSQL checkpointer for the lifetime of this context."""
    url = make_url(database_url)

    if url.get_backend_name() != "postgresql":
        raise ValueError(
            "Workflow checkpoints require PostgreSQL"
        )

    connection_string = url.set(
        drivername="postgresql"
    ).render_as_string(hide_password=False)

    with PostgresSaver.from_conn_string(
        connection_string
    ) as checkpointer:
        yield checkpointer


def initialize_checkpoints(database_url: str) -> None:
    """Create or upgrade LangGraph's checkpoint tables."""
    with open_checkpointer(database_url) as checkpointer:
        checkpointer.setup()


def related_comparison_threads(
    db: Session,
    *,
    procurement_event_id: uuid.UUID | None = None,
    supplier_id: uuid.UUID | None = None,
) -> list[str]:
    """Locate saved comparisons containing evidence that is being removed."""
    thread_ids = list(db.scalars(text("SELECT DISTINCT thread_id FROM checkpoints WHERE checkpoint_ns = ''"))) if db.scalar(text("SELECT to_regclass('checkpoints')")) is not None else []
    # Use this session's connection so checkpoint deletion shares its transaction.
    # PostgresSaver sets dict_row on each cursor; leave SQLAlchemy's factory alone.
    saver = PostgresSaver(cast(Connection[DictRow], db.connection().connection.driver_connection))
    matches: list[str] = []
    for thread_id in thread_ids:
        saved = saver.get_tuple({"configurable": {"thread_id": thread_id}})
        if saved is None:
            continue
        state = saved.checkpoint["channel_values"]
        if procurement_event_id is not None and str(state.get("procurement_event_id")) != str(procurement_event_id):
            continue
        if supplier_id is not None and str(supplier_id) not in {str(value) for value in state.get("supplier_ids", [])}:
            continue
        if "procurement_event_id" in state:
            matches.append(thread_id)
    if db.scalar(text("SELECT to_regclass('comparison_workflow_records')")) is not None:
        statement = select(ComparisonWorkflowRecord.id)
        if procurement_event_id is not None:
            statement = statement.where(ComparisonWorkflowRecord.procurement_event_id == procurement_event_id)
        if supplier_id is not None:
            statement = statement.where(ComparisonWorkflowRecord.supplier_ids.contains([str(supplier_id)]))
        matches.extend(str(value) for value in db.scalars(statement))
    return sorted(set(matches))


def delete_comparison_threads(db: Session, thread_ids: list[str]) -> None:
    lock_records(db, ["workflow-names"], shared=False)
    # PostgresSaver sets dict_row on each cursor; leave SQLAlchemy's factory alone.
    saver = PostgresSaver(cast(Connection[DictRow], db.connection().connection.driver_connection))
    for thread_id in thread_ids:
        saver.delete_thread(thread_id)
    db.execute(delete(ComparisonWorkflowRecord).where(ComparisonWorkflowRecord.id.in_([uuid.UUID(value) for value in thread_ids])))

    renumber_workflows(db)
