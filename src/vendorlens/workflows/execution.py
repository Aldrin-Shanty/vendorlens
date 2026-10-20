from collections.abc import Callable
from typing import TypeVar

from vendorlens.workflows.budget import ExecutionBudget


T = TypeVar("T")


class WorkflowExecutor:
    """Reserve allowances before operations and retain updated usage."""

    def __init__(self, budget: ExecutionBudget):
        self._budget = budget

    @property
    def budget(self) -> ExecutionBudget:
        return self._budget

    def reserve_model_call(self) -> None:
        self._budget = self._budget.reserve_model_call()

    def run_model(self, operation: Callable[[], T]) -> T:
        self.reserve_model_call()
        return operation()

    def run_tool(self, operation: Callable[[], T]) -> T:
        self._budget = self._budget.reserve_tool_call()
        return operation()
