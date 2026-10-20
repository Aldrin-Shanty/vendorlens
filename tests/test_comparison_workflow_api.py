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
