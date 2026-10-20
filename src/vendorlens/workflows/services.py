import uuid

from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.orm import Session

from vendorlens.workflows.budget import ExecutionBudget
from vendorlens.workflows.comparison import build_comparison_graph
from vendorlens.workflows.state import (
    ComparisonWorkflowState,
    create_initial_state,
)

def start_comparison_workflow(
    db: Session,
    *,
    checkpointer: BaseCheckpointSaver,
    procurement_event_id: uuid.UUID,
    supplier_ids: list[uuid.UUID],
    budget: ExecutionBudget | None = None,
) -> uuid.UUID:
    """Run a new comparison until completion, review, or failure."""
    workflow_id = uuid.uuid4()

    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(workflow_id),
        }
    }

    initial_state = create_initial_state(
        procurement_event_id,
        supplier_ids,
        budget=budget,
    )

    graph = build_comparison_graph(
        db,
        checkpointer=checkpointer,
    )

    graph.invoke(initial_state, config=config)

    return workflow_id

class WorkflowNotFoundError(LookupError):
    """The workflow does not exist within the requested event."""


def get_comparison_workflow(
    db: Session,
    *,
    checkpointer: BaseCheckpointSaver,
    procurement_event_id: uuid.UUID,
    workflow_id: uuid.UUID,
) -> ComparisonWorkflowState:
    """Read saved workflow state without executing any nodes."""
    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(workflow_id),
        }
    }

    graph = build_comparison_graph(
        db,
        checkpointer=checkpointer,
    )

    snapshot = graph.get_state(config)
    values = snapshot.values

    if (
        not values
        or values.get("procurement_event_id") != procurement_event_id
    ):
        raise WorkflowNotFoundError(
            "Comparison workflow not found"
        )

    return cast(ComparisonWorkflowState, values)
