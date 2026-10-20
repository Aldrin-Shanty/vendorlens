import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from vendorlens.api.dependencies import get_checkpointer
from vendorlens.api.main import app
from vendorlens.services.retrieval import SearchResult
from vendorlens.services.schemas.supplier_comparison import SupplierFacts
from vendorlens.workflows import comparison as workflow


@pytest.fixture
def workflow_api(monkeypatch):
    saver = InMemorySaver()

    def retrieve(db, procurement_event_id, supplier_id):
        return [
            SearchResult(
                chunk_id=uuid.uuid4(),
                supplier_id=supplier_id,
                supplier_name="Synthetic supplier",
                document_version_id=uuid.uuid4(),
                filename="synthetic.pdf",
                page_number=1,
                text="Product details are available on request.",
                distance=0.1,
            )
        ]

    retrieval = Mock(side_effect=retrieve)
    extraction = Mock(
        side_effect=lambda supplier_name, sources: SupplierFacts(
            supplier_name=supplier_name,
        )
    )

    monkeypatch.setattr(workflow, "retrieve_supplier_evidence", retrieval)
    monkeypatch.setattr(workflow, "extract_facts_from_evidence", extraction)
    app.dependency_overrides[get_checkpointer] = lambda: saver

    try:
        yield saver, retrieval, extraction
    finally:
        app.dependency_overrides.pop(get_checkpointer, None)


def create_comparison_inputs(client):
    event = client.post(
        "/procurement-events",
        json={"title": "Workflow API test"},
    )
    assert event.status_code == 201
    event_id = event.json()["id"]
    supplier_ids = []

    for name in ("Synthetic Dell", "Synthetic HP"):
        supplier = client.post("/suppliers", json={"name": name})
        assert supplier.status_code == 201
        supplier_id = supplier.json()["id"]

        proposal = client.post(
            "/proposals",
            json={
                "supplier_id": supplier_id,
                "procurement_event_id": event_id,
            },
        )
        assert proposal.status_code == 201
        supplier_ids.append(supplier_id)

    return event_id, supplier_ids


def test_start_workflow_returns_saved_review_state(client, workflow_api):
    saver, retrieval, extraction = workflow_api
    event_id, supplier_ids = create_comparison_inputs(client)

    response = client.post(
        f"/procurement-events/{event_id}/comparison-workflows",
        json={"supplier_ids": supplier_ids},
    )

    assert response.status_code == 201
    data = response.json()
    workflow_id = uuid.UUID(data["workflow_id"])

    assert data["procurement_event_id"] == event_id
    assert data["status"] == "awaiting_review"
    assert data["review_decision"] is None
    assert data["error"] is None
    assert data["budget"] == {
        "max_model_calls": 8,
        "max_tool_calls": 2,
        "model_calls_used": 2,
        "tool_calls_used": 2,
    }
    assert [
        entry["supplier_id"]
        for entry in data["comparison"]["suppliers"]
    ] == supplier_ids
    assert len(data["review_issues"]) == 6
    assert {
        issue["reason"] for issue in data["review_issues"]
    } == {"missing_value"}
    assert retrieval.call_count == 2
    assert extraction.call_count == 2

    checkpoint = saver.get_tuple(
        {"configurable": {"thread_id": str(workflow_id)}}
    )
    assert checkpoint is not None
    saved = checkpoint.checkpoint["channel_values"]
    assert saved["status"] == data["status"]
    assert str(saved["procurement_event_id"]) == event_id
    assert saved["comparison"].model_dump(mode="json") == data["comparison"]


def test_start_workflow_rejects_unknown_event(client, workflow_api):
    _, retrieval, extraction = workflow_api

    response = client.post(
        f"/procurement-events/{uuid.uuid4()}/comparison-workflows",
        json={
            "supplier_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Procurement event not found"
    retrieval.assert_not_called()
    extraction.assert_not_called()


@pytest.mark.parametrize(
    "supplier_ids",
    [
        [str(uuid.uuid4())],
        ["invalid-uuid", str(uuid.uuid4())],
        [str(uuid.uuid4()) for _ in range(9)],
        ["00000000-0000-0000-0000-000000000001"] * 2,
    ],
)
def test_start_workflow_rejects_invalid_selection(
    client, workflow_api, supplier_ids
):
    _, retrieval, extraction = workflow_api
    event_id, _ = create_comparison_inputs(client)

    response = client.post(
        f"/procurement-events/{event_id}/comparison-workflows",
        json={"supplier_ids": supplier_ids},
    )

    assert response.status_code == 422
    retrieval.assert_not_called()
    extraction.assert_not_called()


def test_start_workflow_requires_api_key(workflow_api):
    _, retrieval, extraction = workflow_api

    with TestClient(app) as unauthenticated_client:
        response = unauthenticated_client.post(
            f"/procurement-events/{uuid.uuid4()}/comparison-workflows",
            json={
                "supplier_ids": [str(uuid.uuid4()), str(uuid.uuid4())],
            },
        )

    assert response.status_code == 401
    retrieval.assert_not_called()
    extraction.assert_not_called()

def test_get_workflow_returns_saved_state_without_repeating_work(
    client, workflow_api
):
    _, retrieval, extraction = workflow_api
    event_id, supplier_ids = create_comparison_inputs(client)

    started = client.post(
        f"/procurement-events/{event_id}/comparison-workflows",
        json={"supplier_ids": supplier_ids},
    )
    assert started.status_code == 201
    expected = started.json()
    workflow_id = expected["workflow_id"]

    calls_before = (
        retrieval.call_count,
        extraction.call_count,
    )

    for _ in range(2):
        response = client.get(
            f"/procurement-events/{event_id}"
            f"/comparison-workflows/{workflow_id}"
        )

        assert response.status_code == 200
        assert response.json() == expected

    assert (
        retrieval.call_count,
        extraction.call_count,
    ) == calls_before


def test_get_workflow_rejects_unknown_workflow(client, workflow_api):
    _, retrieval, extraction = workflow_api
    event_id, _ = create_comparison_inputs(client)

    response = client.get(
        f"/procurement-events/{event_id}"
        f"/comparison-workflows/{uuid.uuid4()}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Comparison workflow not found"
    retrieval.assert_not_called()
    extraction.assert_not_called()


def test_get_workflow_rejects_wrong_event(client, workflow_api):
    _, retrieval, extraction = workflow_api
    event_id, supplier_ids = create_comparison_inputs(client)

    started = client.post(
        f"/procurement-events/{event_id}/comparison-workflows",
        json={"supplier_ids": supplier_ids},
    )
    assert started.status_code == 201
    workflow_id = started.json()["workflow_id"]

    other_event = client.post(
        "/procurement-events",
        json={"title": "Another procurement event"},
    )
    assert other_event.status_code == 201
    other_event_id = other_event.json()["id"]

    calls_before = (
        retrieval.call_count,
        extraction.call_count,
    )

    response = client.get(
        f"/procurement-events/{other_event_id}"
        f"/comparison-workflows/{workflow_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Comparison workflow not found"
    assert (
        retrieval.call_count,
        extraction.call_count,
    ) == calls_before


def test_get_workflow_rejects_unknown_event(client, workflow_api):
    response = client.get(
        f"/procurement-events/{uuid.uuid4()}"
        f"/comparison-workflows/{uuid.uuid4()}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Procurement event not found"


@pytest.mark.parametrize(
    "event_id, workflow_id",
    [
        ("invalid-uuid", str(uuid.uuid4())),
        (str(uuid.uuid4()), "invalid-uuid"),
    ],
)
def test_get_workflow_rejects_invalid_ids(
    client, workflow_api, event_id, workflow_id
):
    response = client.get(
        f"/procurement-events/{event_id}"
        f"/comparison-workflows/{workflow_id}"
    )

    assert response.status_code == 422


def test_get_workflow_requires_api_key(workflow_api):
    with TestClient(app) as unauthenticated_client:
        response = unauthenticated_client.get(
            f"/procurement-events/{uuid.uuid4()}"
            f"/comparison-workflows/{uuid.uuid4()}"
        )

    assert response.status_code == 401

@pytest.fixture
def started_review_workflow(client, workflow_api):
    event_id, supplier_ids = create_comparison_inputs(client)

    response = client.post(
        f"/procurement-events/{event_id}/comparison-workflows",
        json={"supplier_ids": supplier_ids},
    )
    assert response.status_code == 201

    return event_id, response.json()


@pytest.mark.parametrize(
    "action, expected_status",
    [
        ("acknowledge", "reviewed"),
        ("reject", "rejected"),
    ],
)
def test_review_workflow_preserves_results(
    client,
    workflow_api,
    started_review_workflow,
    action,
    expected_status,
):
    _, retrieval, extraction = workflow_api
    event_id, before = started_review_workflow
    workflow_id = before["workflow_id"]

    base_url = (
        f"/procurement-events/{event_id}"
        f"/comparison-workflows/{workflow_id}"
    )
    decision = {
        "action": action,
        "comment": "Inspected the cited evidence.",
    }
    calls_before = (
        retrieval.call_count,
        extraction.call_count,
    )

    response = client.post(
        f"{base_url}/review",
        json=decision,
    )

    assert response.status_code == 200
    after = response.json()

    assert after["workflow_id"] == workflow_id
    assert after["procurement_event_id"] == event_id
    assert after["status"] == expected_status
    assert after["review_decision"] == decision

    for field in ("comparison", "review_issues", "budget", "error"):
        assert after[field] == before[field]

    saved = client.get(base_url)
    assert saved.status_code == 200
    assert saved.json() == after

    repeated = client.post(
        f"{base_url}/review",
        json=decision,
    )
    assert repeated.status_code == 409

    unchanged = client.get(base_url)
    assert unchanged.status_code == 200
    assert unchanged.json() == after

    assert (
        retrieval.call_count,
        extraction.call_count,
    ) == calls_before


@pytest.mark.parametrize(
    "decision",
    [
        {"action": "approve_purchase", "comment": "Reviewed."},
        {"action": "acknowledge", "comment": "   "},
        {"action": "reject"},
        {
            "action": "reject",
            "comment": "Reviewed.",
            "unexpected": True,
        },
        {"action": "reject", "comment": "x" * 1001},
    ],
)
def test_invalid_review_leaves_workflow_unchanged(
    client, workflow_api, started_review_workflow, decision
):
    _, retrieval, extraction = workflow_api
    event_id, before = started_review_workflow
    workflow_id = before["workflow_id"]

    base_url = (
        f"/procurement-events/{event_id}"
        f"/comparison-workflows/{workflow_id}"
    )
    calls_before = (
        retrieval.call_count,
        extraction.call_count,
    )

    response = client.post(
        f"{base_url}/review",
        json=decision,
    )
    assert response.status_code == 422

    saved = client.get(base_url)
    assert saved.status_code == 200
    assert saved.json() == before

    corrected = client.post(
        f"{base_url}/review",
        json={
            "action": "reject",
            "comment": "The supplied facts need correction.",
        },
    )
    assert corrected.status_code == 200
    assert corrected.json()["status"] == "rejected"

    assert (
        retrieval.call_count,
        extraction.call_count,
    ) == calls_before


@pytest.mark.parametrize(
    "scenario",
    ["unknown_event", "unknown_workflow", "wrong_event"],
)
def test_review_rejects_invalid_scope(
    client, workflow_api, started_review_workflow, scenario
):
    _, retrieval, extraction = workflow_api
    original_event_id, before = started_review_workflow
    event_id = original_event_id
    workflow_id = before["workflow_id"]

    if scenario == "unknown_event":
        event_id = str(uuid.uuid4())
    elif scenario == "unknown_workflow":
        workflow_id = str(uuid.uuid4())
    else:
        other_event = client.post(
            "/procurement-events",
            json={"title": "Another review event"},
        )
        assert other_event.status_code == 201
        event_id = other_event.json()["id"]

    calls_before = (
        retrieval.call_count,
        extraction.call_count,
    )

    response = client.post(
        f"/procurement-events/{event_id}"
        f"/comparison-workflows/{workflow_id}/review",
        json={"action": "reject", "comment": "Reviewed."},
    )

    assert response.status_code == 404

    original = client.get(
        f"/procurement-events/{original_event_id}"
        f"/comparison-workflows/{before['workflow_id']}"
    )
    assert original.status_code == 200
    assert original.json() == before

    assert (
        retrieval.call_count,
        extraction.call_count,
    ) == calls_before


def test_review_requires_api_key(
    workflow_api, started_review_workflow
):
    _, retrieval, extraction = workflow_api
    event_id, before = started_review_workflow
    workflow_id = before["workflow_id"]
    calls_before = (
        retrieval.call_count,
        extraction.call_count,
    )

    with TestClient(app) as unauthenticated_client:
        response = unauthenticated_client.post(
            f"/procurement-events/{event_id}"
            f"/comparison-workflows/{workflow_id}/review",
            json={"action": "reject", "comment": "Reviewed."},
        )

    assert response.status_code == 401
    assert (
        retrieval.call_count,
        extraction.call_count,
    ) == calls_before


def test_workflow_creation_refreshes_numbers_after_deletion(client, workflow_api):
    event_id, suppliers = create_comparison_inputs(client)
    base = f"/procurement-events/{event_id}/comparison-workflows"
    first = client.post(base, json={"supplier_ids": suppliers}).json()
    second = client.post(base, json={"supplier_ids": suppliers[::-1]}).json()
    assert first["name"] == "Workflow API test \u2014 Synthetic Dell + Synthetic HP (1)"
    assert second["name"] == "Workflow API test \u2014 Synthetic Dell + Synthetic HP (2)"
    assert first["created_at"]
    saved = client.get(base).json()
    assert {row["workflow_id"] for row in saved} == {first["workflow_id"], second["workflow_id"]}
    target = f"{base}/{first['workflow_id']}"
    assert client.delete(target).status_code == 409
    assert client.get(target).status_code == 200
    assert client.delete(target + "?confirm=true").status_code == 204
    assert client.get(target).status_code == 404
    remaining = client.get(base).json()
    assert remaining[0]["sequence_number"] == 1
    assert remaining[0]["name"].endswith("(1)")
    third = client.post(base, json={"supplier_ids": suppliers}).json()
    assert third["sequence_number"] == 2
    assert third["name"].endswith("(2)")
    assert len(client.get("/proposals").json()) == 2
    assert len(client.get("/suppliers").json()) == 2


def test_bulk_workflow_delete_covers_all_events_keeps_sources_and_counters(client, workflow_api):
    groups = [create_comparison_inputs(client) for _ in range(2)]
    for event_id, suppliers in groups:
        response = client.post(f"/procurement-events/{event_id}/comparison-workflows", json={"supplier_ids": suppliers})
        assert response.status_code == 201
        assert response.json()["sequence_number"] == 1
    assert len(client.get("/comparison-workflows").json()) == 2
    assert client.delete("/comparison-workflows").status_code == 409
    assert client.delete("/comparison-workflows?confirm=true").status_code == 204
    assert client.get("/comparison-workflows").json() == []
    assert len(client.get("/proposals").json()) == 4
    assert len(client.get("/procurement-events").json()) == 2
    event_id, suppliers = groups[0]
    again = client.post(f"/procurement-events/{event_id}/comparison-workflows", json={"supplier_ids": suppliers})
    assert again.json()["sequence_number"] == 1
    assert client.delete("/comparison-workflows?confirm=true").status_code == 204
    assert client.delete("/comparison-workflows?confirm=true").status_code == 204


def test_workflow_deletion_is_scoped_to_event(client, workflow_api):
    event_id, suppliers = create_comparison_inputs(client)
    other_id, _ = create_comparison_inputs(client)
    base = f"/procurement-events/{event_id}/comparison-workflows"
    run = client.post(base, json={"supplier_ids": suppliers}).json()
    assert client.delete(f"/procurement-events/{other_id}/comparison-workflows/{run['workflow_id']}?confirm=true").status_code == 404
    assert client.get(f"{base}/{run['workflow_id']}").status_code == 200


def test_legacy_postgres_runs_get_names_and_deletion_is_atomic(client, db, monkeypatch):
    import os
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from vendorlens.db.models.comparison_workflow import ComparisonWorkflowRecord
    from vendorlens.workflows.checkpoint import initialize_checkpoints, open_checkpointer
    from vendorlens.workflows.comparison import build_comparison_graph
    from vendorlens.workflows.state import create_initial_state

    event_id, suppliers = create_comparison_inputs(client)
    url = os.environ["TEST_DATABASE_URL"]
    initialize_checkpoints(url)
    ids = [uuid.uuid4(), uuid.uuid4()]
    with open_checkpointer(url) as saver:
        graph = build_comparison_graph(db, checkpointer=saver)
        for workflow_id in ids:
            graph.update_state({"configurable": {"thread_id": str(workflow_id)}}, create_initial_state(uuid.UUID(event_id), [uuid.UUID(value) for value in suppliers]))
        app.dependency_overrides[get_checkpointer] = lambda: saver
        try:
            base = f"/procurement-events/{event_id}/comparison-workflows"
            rows = client.get(base).json()
            assert [row["sequence_number"] for row in rows] == [2, 1]
            assert {row["workflow_id"] for row in rows} == {str(value) for value in ids}
            def fail_commit(self):
                raise RuntimeError("Synthetic commit failure")
            with monkeypatch.context() as patch:
                patch.setattr(Session, "commit", fail_commit)
                with pytest.raises(RuntimeError, match="Synthetic commit failure"):
                    client.delete(f"{base}/{ids[0]}?confirm=true")
            assert saver.get_tuple({"configurable": {"thread_id": str(ids[0])}}) is not None
            assert db.get(ComparisonWorkflowRecord, ids[0]) is not None
            assert client.delete(f"{base}/{ids[0]}?confirm=true").status_code == 204
            assert saver.get_tuple({"configurable": {"thread_id": str(ids[0])}}) is None
            db.expire_all()
            assert db.get(ComparisonWorkflowRecord, ids[0]) is None
            assert saver.get_tuple({"configurable": {"thread_id": str(ids[1])}}) is not None
            assert client.delete("/comparison-workflows?confirm=true").status_code == 204
            assert client.get(base).json() == []
            assert list(db.scalars(select(ComparisonWorkflowRecord))) == []
            assert len(client.get("/proposals").json()) == 2
        finally:
            app.dependency_overrides.pop(get_checkpointer, None)
            for workflow_id in ids:
                saver.delete_thread(str(workflow_id))


def test_creation_and_middle_deletion_keep_group_numbers_consecutive(client, workflow_api):
    event_id, suppliers = create_comparison_inputs(client)
    base = f"/procurement-events/{event_id}/comparison-workflows"
    runs = [client.post(base, json={"supplier_ids": suppliers}).json() for _ in range(3)]
    other_event, other_suppliers = create_comparison_inputs(client)
    other_base = f"/procurement-events/{other_event}/comparison-workflows"
    other = client.post(other_base, json={"supplier_ids": other_suppliers}).json()
    assert client.delete(f"{base}/{runs[1]['workflow_id']}?confirm=true").status_code == 204
    remaining = client.get(base).json()
    assert {row["workflow_id"]: row["sequence_number"] for row in remaining} == {
        runs[0]["workflow_id"]: 1, runs[2]["workflow_id"]: 2,
    }
    renamed = client.get(f"{base}/{runs[2]['workflow_id']}").json()
    assert renamed["name"].endswith("(2)")
    assert renamed["review_issues"] == runs[2]["review_issues"]
    assert client.get(other_base).json()[0]["name"] == other["name"]
    next_run = client.post(base, json={"supplier_ids": suppliers[::-1]}).json()
    assert next_run["sequence_number"] == 3
    refreshed = client.get(f"{base}/{runs[2]['workflow_id']}").json()
    assert refreshed["sequence_number"] == 2
    assert refreshed["name"].endswith("(2)")
    assert refreshed["review_issues"] == runs[2]["review_issues"]
