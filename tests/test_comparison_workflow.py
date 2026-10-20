import uuid
from unittest.mock import Mock
import os

import pytest
from sqlalchemy.orm import Session

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from pydantic import ValidationError

from vendorlens.workflows.checkpoint import (
    initialize_checkpoints,
    open_checkpointer,
)
from vendorlens.services.errors import (
    AIServiceUnavailableError,
    SupplierSelectionError,
)
from vendorlens.services.retrieval import SearchResult
from vendorlens.services.schemas.supplier_comparison import (
    EvidenceJudgment,
    FactEvidence,
    SupplierFacts,
)
from vendorlens.workflows import comparison as workflow
from vendorlens.workflows.budget import ExecutionBudget
from vendorlens.workflows.state import create_initial_state


@pytest.fixture
def operations(monkeypatch):
    supplier_ids = [uuid.uuid4(), uuid.uuid4()]

    selection = Mock(
        return_value=[
            (supplier_ids[0], "Dell"),
            (supplier_ids[1], "HP"),
        ]
    )

    def retrieve(db, event_id, supplier_id):
        return [
            SearchResult(
                chunk_id=uuid.uuid4(),
                supplier_id=supplier_id,
                supplier_name="Supplier",
                document_version_id=uuid.uuid4(),
                filename="proposal.pdf",
                page_number=1,
                text="Unit price: 1200 USD. Warranty: 3 years.",
                distance=0.1,
            )
        ]

    retrieval = Mock(side_effect=retrieve)

    def extract(name, sources):
        return SupplierFacts(
            supplier_name=name,
            unit_price=1200,
            currency="USD",
            unit_price_evidence=FactEvidence(evidence_ids=[1]),
            warranty_years=3,
            warranty_evidence=FactEvidence(evidence_ids=[1]),
        )

    extraction = Mock(side_effect=extract)

    def judge(facts, evidence, *, before_model_call):
        # Simulate one execution for each of the two extracted facts.
        before_model_call()
        before_model_call()
        return EvidenceJudgment(
            status="checked",
            model="test-model",
        )

    judgment = Mock(side_effect=judge)

    monkeypatch.setattr(
        workflow, "validate_supplier_selection", selection
    )
    monkeypatch.setattr(
        workflow, "retrieve_supplier_evidence", retrieval
    )
    monkeypatch.setattr(
        workflow, "extract_facts_from_evidence", extraction
    )
    monkeypatch.setattr(
        workflow, "judge_supplier_facts", judgment
    )

    return supplier_ids, selection, retrieval, extraction, judgment


def invoke_graph(supplier_ids, budget):
    initial = create_initial_state(
        uuid.uuid4(),
        supplier_ids,
        budget=budget,
    )

    graph = workflow.build_comparison_graph(
        Mock(spec=Session),
        checkpointer=InMemorySaver(),
    )

    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(uuid.uuid4()),
        }
    }

    return initial, graph.invoke(initial, config=config)


def test_completed_comparison_counts_every_operation(operations):
    supplier_ids, _, retrieval, extraction, judgment = operations

    initial, result = invoke_graph(
        supplier_ids,
        ExecutionBudget(max_model_calls=6, max_tool_calls=2),
    )

    comparison = result["comparison"]

    assert result["status"] == "awaiting_review"
    assert result["review_issues"]
    assert result["__interrupt__"]

    assert result["error"] is None
    assert comparison is not None
    assert [
        entry.supplier_id for entry in comparison.suppliers
    ] == supplier_ids

    # Two Qwen executions + four simulated NLI executions.
    assert result["budget"].model_calls_used == 6
    assert result["budget"].tool_calls_used == 2

    assert retrieval.call_count == 2
    assert extraction.call_count == 2
    assert judgment.call_count == 2

    assert initial["budget"].model_calls_used == 0
    assert "comparison" not in initial


def test_zero_tool_budget_blocks_retrieval(operations):
    supplier_ids, _, retrieval, extraction, judgment = operations

    _, result = invoke_graph(
        supplier_ids,
        ExecutionBudget(max_tool_calls=0),
    )

    assert result["status"] == "stopped"
    assert result["comparison"] is None
    assert result["budget"].tool_calls_used == 0

    retrieval.assert_not_called()
    extraction.assert_not_called()
    judgment.assert_not_called()


def test_zero_model_budget_blocks_qwen(operations):
    supplier_ids, _, retrieval, extraction, judgment = operations

    _, result = invoke_graph(
        supplier_ids,
        ExecutionBudget(max_model_calls=0),
    )

    assert result["status"] == "stopped"
    assert result["budget"].tool_calls_used == 1
    assert result["budget"].model_calls_used == 0

    retrieval.assert_called_once()
    extraction.assert_not_called()
    judgment.assert_not_called()


def test_nli_cannot_exceed_remaining_model_allowance(operations):
    supplier_ids, _, retrieval, extraction, judgment = operations

    _, result = invoke_graph(
        supplier_ids,
        ExecutionBudget(max_model_calls=2),
    )

    # Qwen consumes one. The first NLI execution consumes one.
    # The second NLI execution is blocked.
    assert result["status"] == "stopped"
    assert result["comparison"] is None
    assert result["budget"].model_calls_used == 2

    assert retrieval.call_count == 1
    assert extraction.call_count == 1
    assert judgment.call_count == 1


def test_failed_extraction_remains_counted(operations):
    supplier_ids, _, retrieval, extraction, judgment = operations
    extraction.side_effect = AIServiceUnavailableError("Unavailable")

    _, result = invoke_graph(
        supplier_ids,
        ExecutionBudget(),
    )

    assert result["status"] == "failed"
    assert result["comparison"] is None
    assert result["budget"].model_calls_used == 1
    assert result["budget"].tool_calls_used == 1
    assert result["error"] == (
        "Comparison failed: AIServiceUnavailableError"
    )

    judgment.assert_not_called()


def test_invalid_selection_stops_before_expensive_operations(operations):
    supplier_ids, selection, retrieval, extraction, judgment = operations
    selection.side_effect = SupplierSelectionError("Invalid selection")

    _, result = invoke_graph(
        supplier_ids,
        ExecutionBudget(),
    )

    assert result["status"] == "failed"
    assert result["budget"].model_calls_used == 0
    assert result["budget"].tool_calls_used == 0

    retrieval.assert_not_called()
    extraction.assert_not_called()
    judgment.assert_not_called()

def test_graph_completes_when_assessment_finds_no_issues(
    operations, monkeypatch
):
    supplier_ids, _, _, _, _ = operations
    assessment = Mock(return_value=[])

    monkeypatch.setattr(
        workflow,
        "collect_review_issues",
        assessment,
    )

    _, result = invoke_graph(
        supplier_ids,
        ExecutionBudget(max_model_calls=6, max_tool_calls=2),
    )

    assert result["status"] == "completed"
    assert result["review_issues"] == []
    assert not result.get("__interrupt__")
    assessment.assert_called_once_with(result["comparison"])


def test_stopped_graph_bypasses_review_assessment(
    operations, monkeypatch
):
    supplier_ids, _, _, _, _ = operations
    assessment = Mock()

    monkeypatch.setattr(
        workflow,
        "collect_review_issues",
        assessment,
    )

    _, result = invoke_graph(
        supplier_ids,
        ExecutionBudget(max_tool_calls=0),
    )

    assert result["status"] == "stopped"
    assessment.assert_not_called()


def test_failed_graph_bypasses_review_assessment(
    operations, monkeypatch
):
    supplier_ids, selection, _, _, _ = operations
    selection.side_effect = SupplierSelectionError("Invalid selection")
    assessment = Mock()

    monkeypatch.setattr(
        workflow,
        "collect_review_issues",
        assessment,
    )

    _, result = invoke_graph(supplier_ids, ExecutionBudget())

    assert result["status"] == "failed"
    assessment.assert_not_called()


def start_review_run(supplier_ids):
    graph = workflow.build_comparison_graph(
        Mock(spec=Session),
        checkpointer=InMemorySaver(),
    )
    config: RunnableConfig = {"configurable": {"thread_id": str(uuid.uuid4())}}
    initial = create_initial_state(
        uuid.uuid4(),
        supplier_ids,
        budget=ExecutionBudget(max_model_calls=6, max_tool_calls=2),
    )
    return graph, config, graph.invoke(initial, config=config)


def test_review_path_really_pauses(operations):
    supplier_ids, _, _, _, _ = operations
    graph, config, paused = start_review_run(supplier_ids)

    assert paused["status"] == "awaiting_review"
    assert "review_decision" not in paused
    payload = paused["__interrupt__"][0].value
    assert payload["type"] == "supplier_comparison_review"
    assert payload["issues"] == [
        issue.model_dump(mode="json") for issue in paused["review_issues"]
    ]
    assert payload["comparison"] == paused["comparison"].model_dump(mode="json")
    assert graph.get_state(config).next == ("human_review",)


@pytest.mark.parametrize("action, expected_status", [
    ("acknowledge", "reviewed"),
    ("reject", "rejected"),
])
def test_resume_preserves_results_without_repeating_work(operations, action, expected_status):
    supplier_ids, *services = operations
    graph, config, paused = start_review_run(supplier_ids)
    comparison_before = paused["comparison"].model_dump()
    issues_before = [issue.model_dump() for issue in paused["review_issues"]]
    budget_before = paused["budget"].model_dump()
    calls_before = [service.call_count for service in services]

    result = graph.invoke(
        Command(resume={"action": action, "comment": "Inspected the cited evidence."}),
        config=config,
    )

    assert result["status"] == expected_status
    assert result["review_decision"].action == action
    assert result["comparison"].model_dump() == comparison_before
    assert [issue.model_dump() for issue in result["review_issues"]] == issues_before
    assert result["budget"].model_dump() == budget_before
    assert [service.call_count for service in services] == calls_before
    assert graph.get_state(config).next == ()
    assert not result.get("__interrupt__")


@pytest.mark.parametrize("invalid_response", [
    {"action": "approve_purchase", "comment": "Invalid action."},
    {"action": "acknowledge", "comment": "   "},
    {"action": "reject"},
    {"action": "reject", "comment": "Reviewed.", "unexpected": True},
])
def test_invalid_review_response_can_be_corrected(operations, invalid_response):
    supplier_ids, *services = operations
    graph, config, _ = start_review_run(supplier_ids)
    calls_before = [service.call_count for service in services]

    with pytest.raises(ValidationError):
        graph.invoke(Command(resume=invalid_response), config=config)

    assert graph.get_state(config).next == ("human_review",)
    result = graph.invoke(
        Command(resume={"action": "reject", "comment": "The warranty needs correction."}),
        config=config,
    )
    assert result["status"] == "rejected"
    assert [service.call_count for service in services] == calls_before

@pytest.mark.parametrize(
    "action, expected_status",
    [
        ("acknowledge", "reviewed"),
        ("reject", "rejected"),
    ],
)
def test_postgres_resumes_with_new_graph_and_connection(
    operations, action, expected_status
):
    supplier_ids, *services = operations
    database_url = os.environ["TEST_DATABASE_URL"]

    initialize_checkpoints(database_url)

    thread_id = str(uuid.uuid4())
    config: RunnableConfig = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    initial = create_initial_state(
        uuid.uuid4(),
        supplier_ids,
        budget=ExecutionBudget(
            max_model_calls=6,
            max_tool_calls=2,
        ),
    )

    try:
        with open_checkpointer(database_url) as first_saver:
            first_graph = workflow.build_comparison_graph(
                Mock(spec=Session),
                checkpointer=first_saver,
            )

            paused = first_graph.invoke(
                initial,
                config=config,
            )

            assert paused["status"] == "awaiting_review"
            assert paused["__interrupt__"]

            comparison_before = paused["comparison"].model_dump()
            issues_before = [
                issue.model_dump()
                for issue in paused["review_issues"]
            ]
            budget_before = paused["budget"].model_dump()

        # Discard the first graph and close its checkpoint connection.
        del first_graph
        del first_saver
        del paused

        calls_before = [
            service.call_count
            for service in services
        ]

        with open_checkpointer(database_url) as second_saver:
            second_graph = workflow.build_comparison_graph(
                Mock(spec=Session),
                checkpointer=second_saver,
            )

            snapshot = second_graph.get_state(config)

            assert snapshot.next == ("human_review",)
            assert snapshot.values["status"] == "awaiting_review"

            result = second_graph.invoke(
                Command(
                    resume={
                        "action": action,
                        "comment": (
                            "Reviewed evidence after reopening "
                            "the saved workflow."
                        ),
                    }
                ),
                config=config,
            )

            assert result["status"] == expected_status
            assert result["review_decision"].action == action

            assert (
                result["comparison"].model_dump()
                == comparison_before
            )

            assert [
                issue.model_dump()
                for issue in result["review_issues"]
            ] == issues_before

            assert result["budget"].model_dump() == budget_before

            assert [
                service.call_count
                for service in services
            ] == calls_before

            assert second_graph.get_state(config).next == ()

    finally:
        with open_checkpointer(database_url) as cleanup_saver:
            cleanup_saver.delete_thread(thread_id)

def test_postgres_checkpoint_does_not_load_another_run(
    operations,
):
    supplier_ids, _, _, _, _ = operations
    database_url = os.environ["TEST_DATABASE_URL"]

    initialize_checkpoints(database_url)

    saved_thread_id = str(uuid.uuid4())

    saved_config: RunnableConfig = {
        "configurable": {
            "thread_id": saved_thread_id,
        }
    }

    other_config: RunnableConfig = {
        "configurable": {
            "thread_id": str(uuid.uuid4()),
        }
    }

    try:
        with open_checkpointer(database_url) as saver:
            graph = workflow.build_comparison_graph(
                Mock(spec=Session),
                checkpointer=saver,
            )

            graph.invoke(
                create_initial_state(
                    uuid.uuid4(),
                    supplier_ids,
                    budget=ExecutionBudget(
                        max_model_calls=6,
                        max_tool_calls=2,
                    ),
                ),
                config=saved_config,
            )

            assert (
                graph.get_state(saved_config).next
                == ("human_review",)
            )

            other_snapshot = graph.get_state(other_config)

            assert not other_snapshot.values
            assert other_snapshot.next == ()

    finally:
        with open_checkpointer(database_url) as saver:
            saver.delete_thread(saved_thread_id)

def test_start_service_saves_workflow_under_returned_id(operations):
    from vendorlens.workflows.services import start_comparison_workflow

    supplier_ids, _, _, _, _ = operations
    event_id = uuid.uuid4()
    saver = InMemorySaver()
    db = Mock(spec=Session)

    workflow_id = start_comparison_workflow(
        db,
        checkpointer=saver,
        procurement_event_id=event_id,
        supplier_ids=supplier_ids,
        budget=ExecutionBudget(
            max_model_calls=6,
            max_tool_calls=2,
        ),
    )

    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(workflow_id),
        }
    }

    graph = workflow.build_comparison_graph(
        db,
        checkpointer=saver,
    )
    snapshot = graph.get_state(config)

    assert isinstance(workflow_id, uuid.UUID)
    assert snapshot.values["procurement_event_id"] == event_id
    assert snapshot.values["supplier_ids"] == supplier_ids
    assert snapshot.values["status"] == "awaiting_review"
    assert snapshot.next == ("human_review",)

def test_get_service_reads_state_without_repeating_work(operations):
    from vendorlens.workflows.services import (
        get_comparison_workflow,
        start_comparison_workflow,
    )

    supplier_ids, *services = operations
    event_id = uuid.uuid4()
    saver = InMemorySaver()
    db = Mock(spec=Session)

    workflow_id = start_comparison_workflow(
        db,
        checkpointer=saver,
        procurement_event_id=event_id,
        supplier_ids=supplier_ids,
        budget=ExecutionBudget(
            max_model_calls=6,
            max_tool_calls=2,
        ),
    )
    calls_before = [service.call_count for service in services]

    state = get_comparison_workflow(
        db,
        checkpointer=saver,
        procurement_event_id=event_id,
        workflow_id=workflow_id,
    )

    assert state["procurement_event_id"] == event_id
    assert state["supplier_ids"] == supplier_ids
    assert state.get("status") == "awaiting_review"
    assert state.get("comparison") is not None
    assert state.get("review_issues")
    assert [service.call_count for service in services] == calls_before


@pytest.mark.parametrize("wrong_event", [False, True])
def test_get_service_rejects_unknown_or_wrong_event_workflow(
    operations, wrong_event
):
    from vendorlens.services.errors import WorkflowNotFoundError
    from vendorlens.workflows.services import (
        get_comparison_workflow,
        start_comparison_workflow,
    )

    supplier_ids, *services = operations
    event_id = uuid.uuid4()
    saver = InMemorySaver()
    db = Mock(spec=Session)

    workflow_id = start_comparison_workflow(
        db,
        checkpointer=saver,
        procurement_event_id=event_id,
        supplier_ids=supplier_ids,
        budget=ExecutionBudget(
            max_model_calls=6,
            max_tool_calls=2,
        ),
    )
    calls_before = [service.call_count for service in services]

    with pytest.raises(WorkflowNotFoundError):
        get_comparison_workflow(
            db,
            checkpointer=saver,
            procurement_event_id=(
                uuid.uuid4() if wrong_event else event_id
            ),
            workflow_id=(
                workflow_id if wrong_event else uuid.uuid4()
            ),
        )

    assert [service.call_count for service in services] == calls_before

@pytest.mark.parametrize(
    "action, expected_status",
    [
        ("acknowledge", "reviewed"),
        ("reject", "rejected"),
    ],
)
def test_resume_service_records_decision_without_repeating_work(
    operations, action, expected_status
):
    from vendorlens.services.errors import WorkflowReviewConflictError
    from vendorlens.workflows.review import ReviewDecision
    from vendorlens.workflows.services import (
        get_comparison_workflow,
        resume_comparison_workflow,
        start_comparison_workflow,
    )

    supplier_ids, *services = operations
    event_id = uuid.uuid4()
    saver = InMemorySaver()
    db = Mock(spec=Session)

    workflow_id = start_comparison_workflow(
        db,
        checkpointer=saver,
        procurement_event_id=event_id,
        supplier_ids=supplier_ids,
        budget=ExecutionBudget(
            max_model_calls=6,
            max_tool_calls=2,
        ),
    )

    before = get_comparison_workflow(
        db,
        checkpointer=saver,
        procurement_event_id=event_id,
        workflow_id=workflow_id,
    )
    comparison_before_value = before.get("comparison")
    assert comparison_before_value is not None
    comparison_before = comparison_before_value.model_dump()
    budget_before = before["budget"].model_dump()
    issues_before = [
        issue.model_dump()
        for issue in before.get("review_issues", [])
    ]
    calls_before = [service.call_count for service in services]

    decision = ReviewDecision(
        action=action,
        comment="Inspected the cited evidence.",
    )

    result = resume_comparison_workflow(
        db,
        checkpointer=saver,
        procurement_event_id=event_id,
        workflow_id=workflow_id,
        decision=decision,
    )

    assert result.get("status") == expected_status
    assert result.get("review_decision") == decision
    comparison_after = result.get("comparison")
    assert comparison_after is not None
    assert comparison_after.model_dump() == comparison_before
    assert result["budget"].model_dump() == budget_before
    assert [
        issue.model_dump()
        for issue in result.get("review_issues", [])
    ] == issues_before

    with pytest.raises(WorkflowReviewConflictError):
        resume_comparison_workflow(
            db,
            checkpointer=saver,
            procurement_event_id=event_id,
            workflow_id=workflow_id,
            decision=decision,
        )

    assert [service.call_count for service in services] == calls_before
