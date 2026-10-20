from pydantic import BaseModel, ConfigDict, Field, model_validator


class BudgetExceededError(Exception):
    """The workflow cannot perform another operation within its budget."""


class ExecutionBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_model_calls: int = Field(default=5, ge=0)
    max_tool_calls: int = Field(default=8, ge=0)
    model_calls_used: int = Field(default=0, ge=0)
    tool_calls_used: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_usage(self):
        if self.model_calls_used > self.max_model_calls:
            raise ValueError("Model usage cannot exceed its limit")
        if self.tool_calls_used > self.max_tool_calls:
            raise ValueError("Tool usage cannot exceed its limit")
        return self

    def reserve_model_call(self) -> "ExecutionBudget":
        if self.model_calls_used >= self.max_model_calls:
            raise BudgetExceededError("Model-call budget exhausted")
        return self.model_copy(
            update={"model_calls_used": self.model_calls_used + 1}
        )

    def reserve_tool_call(self) -> "ExecutionBudget":
        if self.tool_calls_used >= self.max_tool_calls:
            raise BudgetExceededError("Tool-call budget exhausted")
        return self.model_copy(
            update={"tool_calls_used": self.tool_calls_used + 1}
        )
