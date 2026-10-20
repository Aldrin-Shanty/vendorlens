import uuid

from vendorlens.workflows.budget import ExecutionBudget
from vendorlens.workflows.state import create_initial_state


def test_initial_state_contains_request_and_default_budget():
    event_id = uuid.uuid4()
    supplier_ids = [uuid.uuid4(), uuid.uuid4()]

    state = create_initial_state(event_id, supplier_ids)

    assert state["procurement_event_id"] == event_id
    assert state["supplier_ids"] == supplier_ids
    assert state["budget"] == ExecutionBudget()
    assert "comparison" not in state


def test_initial_state_preserves_supplied_budget():
    budget = ExecutionBudget(
        max_model_calls=2,
        max_tool_calls=3,
        model_calls_used=1,
    )

    state = create_initial_state(
        uuid.uuid4(),
        [uuid.uuid4(), uuid.uuid4()],
        budget=budget,
    )

    assert state["budget"] is budget
    assert state["budget"].model_calls_used == 1
    assert state["budget"].max_model_calls == 2


def test_initial_state_copies_supplier_selection():
    supplier_ids = [uuid.uuid4(), uuid.uuid4()]

    state = create_initial_state(uuid.uuid4(), supplier_ids)
    original_selection = list(supplier_ids)

    supplier_ids.append(uuid.uuid4())

    assert state["supplier_ids"] == original_selection
    assert state["supplier_ids"] is not supplier_ids


def test_separate_runs_receive_separate_default_budgets():
    supplier_ids = [uuid.uuid4(), uuid.uuid4()]

    first = create_initial_state(uuid.uuid4(), supplier_ids)
    second = create_initial_state(uuid.uuid4(), supplier_ids)

    assert first["budget"] is not second["budget"]

    first["budget"] = first["budget"].reserve_model_call()

    assert first["budget"].model_calls_used == 1
    assert second["budget"].model_calls_used == 0
