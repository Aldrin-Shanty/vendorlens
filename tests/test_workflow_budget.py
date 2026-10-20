import pytest
from pydantic import ValidationError

from vendorlens.workflows.budget import (
    BudgetExceededError,
    ExecutionBudget,
)


def test_model_reservation_returns_updated_budget():
    budget = ExecutionBudget(max_model_calls=2)

    updated = budget.reserve_model_call()

    assert budget.model_calls_used == 0
    assert updated.model_calls_used == 1
    assert updated.tool_calls_used == 0


def test_model_budget_blocks_an_extra_call():
    budget = ExecutionBudget(max_model_calls=2)

    budget = budget.reserve_model_call()
    budget = budget.reserve_model_call()

    with pytest.raises(
        BudgetExceededError,
        match="Model-call budget exhausted",
    ):
        budget = budget.reserve_model_call()


def test_tool_budget_blocks_an_extra_call():
    budget = ExecutionBudget(max_tool_calls=1)

    budget = budget.reserve_tool_call()

    assert budget.tool_calls_used == 1
    assert budget.model_calls_used == 0

    with pytest.raises(
        BudgetExceededError,
        match="Tool-call budget exhausted",
    ):
        budget = budget.reserve_tool_call()


def test_zero_budget_blocks_operations():
    budget = ExecutionBudget(
        max_model_calls=0,
        max_tool_calls=0,
    )

    with pytest.raises(BudgetExceededError):
        budget = budget.reserve_model_call()

    with pytest.raises(BudgetExceededError):
        budget = budget.reserve_tool_call()


@pytest.mark.parametrize(
    "values",
    [
        {"max_model_calls": -1},
        {"max_tool_calls": -1},
        {"model_calls_used": -1},
        {"tool_calls_used": -1},
        {"max_model_calls": 1, "model_calls_used": 2},
        {"max_tool_calls": 1, "tool_calls_used": 2},
    ],
)
def test_invalid_budget_state_is_rejected(values):
    with pytest.raises(ValidationError):
        ExecutionBudget.model_validate(values)


@pytest.mark.parametrize("field, value", [
    ("model_calls_used", -1),
    ("tool_calls_used", -1),
    ("model_calls_used", 6),
    ("tool_calls_used", 9),
])
def test_invalid_assignment_preserves_budget(field, value):
    budget = ExecutionBudget()
    before = budget.model_dump()
    with pytest.raises(ValidationError):
        setattr(budget, field, value)
    assert budget.model_dump() == before


def test_budget_rejects_direct_modification():
    budget = ExecutionBudget()
    with pytest.raises(ValidationError):
        setattr(budget, "model_calls_used", 1)
    assert budget.model_calls_used == 0


def test_limit_cannot_be_lowered_below_usage():
    budget = ExecutionBudget(model_calls_used=2)
    with pytest.raises(ValidationError):
        budget.max_model_calls = 1
    assert budget.max_model_calls == 5
    assert budget.model_calls_used == 2


def test_budget_round_trip_preserves_usage():
    budget = ExecutionBudget()
    budget = budget.reserve_model_call()
    restored = ExecutionBudget.model_validate_json(budget.model_dump_json())
    assert restored == budget
    updated = restored.reserve_model_call()
    assert budget.model_calls_used == 1
    assert restored.model_calls_used == 1
    assert updated.model_calls_used == 2
