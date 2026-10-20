import uuid

from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from sqlalchemy.orm import Session


from vendorlens.workflows.review import ReviewDecision
from vendorlens.services.data_locks import lock_comparison_data
from vendorlens.services.data_locks import lock_records
from vendorlens.workflows.budget import ExecutionBudget
from vendorlens.workflows.comparison import build_comparison_graph
from vendorlens.services.errors import (
    WorkflowNotFoundError,
    WorkflowReviewConflictError,
)
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
    workflow_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Run a new comparison until completion, review, or failure."""
    workflow_id = workflow_id if workflow_id is not None else uuid.uuid4()
    lock_records(db, ["workflow-catalog"], shared=True)
    lock_records(db, [f"workflow:{workflow_id}"], shared=False)
    lock_comparison_data(db, procurement_event_id, supplier_ids)

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

def resume_comparison_workflow(
    db: Session,
    *,
    checkpointer: BaseCheckpointSaver,
    procurement_event_id: uuid.UUID,
    workflow_id: uuid.UUID,
    decision: ReviewDecision,
) -> ComparisonWorkflowState:
    """Submit a decision to a workflow paused for human review."""
    lock_records(db, ["workflow-catalog"], shared=True)
    lock_records(db, [f"workflow:{workflow_id}"], shared=False)
    state = get_comparison_workflow(
        db,
        checkpointer=checkpointer,
        procurement_event_id=procurement_event_id,
        workflow_id=workflow_id,
    )

    lock_comparison_data(db, procurement_event_id, state["supplier_ids"])

    if state.get("status") != "awaiting_review":
        raise WorkflowReviewConflictError(
            "Comparison workflow is not awaiting review"
        )

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

    if snapshot.next != ("human_review",):
        raise WorkflowReviewConflictError(
            "Comparison workflow is not paused for human review"
        )

    result = graph.invoke(
        Command(resume=decision.model_dump(mode="json")),
        config=config,
    )

    return cast(ComparisonWorkflowState, result)
