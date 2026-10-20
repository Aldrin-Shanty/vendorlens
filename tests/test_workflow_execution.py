from unittest.mock import Mock

import pytest

from vendorlens.workflows.budget import (
    BudgetExceededError,
    ExecutionBudget,
)
from vendorlens.workflows.execution import WorkflowExecutor


def test_model_reserves_before_execution():
    original = ExecutionBudget(max_model_calls=1)
    executor = WorkflowExecutor(original)

    def operation():
        assert executor.budget.model_calls_used == 1
        return "facts"

    assert executor.run_model(operation) == "facts"
    assert original.model_calls_used == 0
    assert executor.budget.tool_calls_used == 0


def test_tool_reserves_before_execution():
    executor = WorkflowExecutor(ExecutionBudget(max_tool_calls=1))

    def operation():
        assert executor.budget.tool_calls_used == 1
        return ["source"]

    assert executor.run_tool(operation) == ["source"]
    assert executor.budget.model_calls_used == 0


@pytest.mark.parametrize("kind", ["model", "tool"])
def test_exhausted_budget_blocks_operation(kind):
    executor = WorkflowExecutor(ExecutionBudget(max_model_calls=0, max_tool_calls=0))
    operation = Mock()

    with pytest.raises(BudgetExceededError):
        if kind == "model":
            executor.run_model(operation)
        else:
            executor.run_tool(operation)

    operation.assert_not_called()


@pytest.mark.parametrize("kind", ["model", "tool"])
def test_failed_operation_remains_counted(kind):
    executor = WorkflowExecutor(ExecutionBudget())
    operation = Mock(
        side_effect=RuntimeError("Operation failed")
    )

    with pytest.raises(RuntimeError, match="Operation failed"):
        if kind == "model":
            executor.run_model(operation)
        else:
            executor.run_tool(operation)

    operation.assert_called_once_with()

    assert executor.budget.model_calls_used == (
        1 if kind == "model" else 0
    )
    assert executor.budget.tool_calls_used == (
        1 if kind == "tool" else 0
    )


def test_callback_and_wrapped_calls_share_budget():
    executor = WorkflowExecutor(ExecutionBudget(max_model_calls=2))

    executor.reserve_model_call()
    executor.run_model(lambda: "result")

    assert executor.budget.model_calls_used == 2

    with pytest.raises(BudgetExceededError):
        executor.reserve_model_call()
