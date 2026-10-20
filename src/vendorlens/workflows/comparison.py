import httpx
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError
from sqlalchemy.orm import Session
from typing import Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command, interrupt

from vendorlens.workflows.review import (
    ReviewDecision,
    collect_review_issues,
)
from vendorlens.services.comparison import validate_supplier_selection
from vendorlens.services.errors import (
    AIOutputError,
    AIServiceUnavailableError,
    EvidenceValidationError,
    SupplierSelectionError,
)
from vendorlens.services.evidence_judgment import judge_supplier_facts
from vendorlens.services.fact_extraction import (
    build_evidence_references,
    extract_facts_from_evidence,
    retrieve_supplier_evidence,
    validate_supplier_facts,
)
from vendorlens.services.schemas.supplier_comparison import (
    SupplierComparison,
    SupplierComparisonEntry,
)
from vendorlens.workflows.budget import BudgetExceededError
from vendorlens.workflows.execution import WorkflowExecutor
from vendorlens.workflows.state import (
    ComparisonWorkflowState,
    ComparisonWorkflowUpdate,
)

def route_after_comparison(
    state: ComparisonWorkflowState,
) -> Literal["assess_review", "finish"]:
    if state.get("status") == "completed":
        return "assess_review"

    return "finish"


def assess_review(
    state: ComparisonWorkflowState,
) -> Command[Literal["human_review", "__end__"]]:
    comparison = state.get("comparison")

    if comparison is None:
        raise ValueError(
            "Review assessment requires a comparison"
        )

    issues = collect_review_issues(comparison)

    update: ComparisonWorkflowUpdate = {
        "review_issues": issues,
        "status": "awaiting_review" if issues else "completed",
    }
    destination: Literal["human_review", "__end__"] = (
        "human_review" if issues else "__end__"
    )
    return Command[Literal["human_review", "__end__"]](
        update=update,
        goto=destination,
    )


def human_review(
    state: ComparisonWorkflowState,
) -> ComparisonWorkflowUpdate:
    comparison = state.get("comparison")
    issues = state.get("review_issues", [])

    if comparison is None or not issues:
        raise ValueError(
            "Human review requires a comparison and review issues"
        )

    decision = interrupt(
        {
            "type": "supplier_comparison_review",
            "comparison": comparison.model_dump(mode="json"),
            "issues": [
                issue.model_dump(mode="json")
                for issue in issues
            ],
            "instructions": (
                "Inspect the comparison and cited evidence. "
                "Acknowledge the issues or reject the result. "
                "This decision does not approve a purchase."
            ),
        },
        response_schema=ReviewDecision,
    )

    decision = ReviewDecision.model_validate(decision)

    return {
        "review_decision": decision,
        "status": (
            "reviewed"
            if decision.action == "acknowledge"
            else "rejected"
        ),
    }

def build_comparison_graph(
    db: Session,
    *,
    checkpointer: BaseCheckpointSaver,
):
    """Build a comparison graph with explicit operation budgets."""

    def run_comparison(
        state: ComparisonWorkflowState,
    ) -> ComparisonWorkflowUpdate:
        executor = WorkflowExecutor(state["budget"])

        try:
            suppliers = validate_supplier_selection(
                db,
                state["procurement_event_id"],
                state["supplier_ids"],
            )

            entries: list[SupplierComparisonEntry] = []

            for supplier_id, supplier_name in suppliers:
                sources = executor.run_tool(
                    lambda: retrieve_supplier_evidence(
                        db,
                        state["procurement_event_id"],
                        supplier_id,
                    )
                )

                facts = executor.run_model(
                    lambda: extract_facts_from_evidence(
                        supplier_name,
                        sources,
                    )
                )

                validate_supplier_facts(
                    facts,
                    supplier_id,
                    supplier_name,
                    sources,
                )

                evidence = build_evidence_references(
                    facts,
                    sources,
                )

                judgment = judge_supplier_facts(
                    facts,
                    evidence,
                    before_model_call=executor.reserve_model_call,
                )

                entries.append(
                    SupplierComparisonEntry(
                        supplier_id=supplier_id,
                        facts=facts,
                        evidence=evidence,
                        judgment=judgment,
                    )
                )

            comparison = SupplierComparison(
                procurement_event_id=state["procurement_event_id"],
                suppliers=entries,
            )

        except BudgetExceededError as exc:
            return {
                "budget": executor.budget,
                "comparison": None,
                "status": "stopped",
                "error": str(exc),
            }

        except (
            SupplierSelectionError,
            EvidenceValidationError,
            AIOutputError,
            AIServiceUnavailableError,
            ValidationError,
            httpx.HTTPError,
        ) as exc:
            return {
                "budget": executor.budget,
                "comparison": None,
                "status": "failed",
                "error": f"Comparison failed: {type(exc).__name__}",
            }

        return {
            "budget": executor.budget,
            "comparison": comparison,
            "status": "completed",
            "error": None,
        }

    builder = StateGraph(ComparisonWorkflowState)

    builder.add_node("compare_suppliers", run_comparison)
    builder.add_node("assess_review", assess_review)
    builder.add_node("human_review", human_review)

    builder.add_edge(START, "compare_suppliers")

    builder.add_conditional_edges(
        "compare_suppliers",
        route_after_comparison,
        {
            "assess_review": "assess_review",
            "finish": END,
        },
    )

    builder.add_edge("human_review", END)

    return builder.compile(checkpointer=checkpointer)
