import uuid
import os

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from vendorlens.api.main import app


load_dotenv()

API_KEY = os.getenv("API_KEY")

if API_KEY is None:
    raise RuntimeError("API_KEY environment variable is not set")


client = TestClient(
    app,
    headers={"X-API-Key": API_KEY},
)


def create_supplier():
    response = client.post(
        "/suppliers",
        json={"name": "Test Supplier"},
    )

    assert response.status_code == 201

    return response.json()


def create_procurement_event():
    response = client.post(
        "/procurement-events",
        json={"title": "Test Procurement Event"},
    )

    assert response.status_code == 201

    return response.json()


def test_create_proposal():
    supplier = create_supplier()
    procurement_event = create_procurement_event()

    response = client.post(
        "/proposals",
        json={
            "supplier_id": supplier["id"],
            "procurement_event_id": procurement_event["id"],
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert "id" in data
    assert data["supplier_id"] == supplier["id"]
    assert (
        data["procurement_event_id"]
        == procurement_event["id"]
    )


def test_get_proposals():
    supplier = create_supplier()
    procurement_event = create_procurement_event()

    create_response = client.post(
        "/proposals",
        json={
            "supplier_id": supplier["id"],
            "procurement_event_id": procurement_event["id"],
        },
    )

    assert create_response.status_code == 201

    response = client.get("/proposals")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["supplier_id"] == supplier["id"]
    assert (
        data[0]["procurement_event_id"]
        == procurement_event["id"]
    )


def test_get_proposal():
    supplier = create_supplier()
    procurement_event = create_procurement_event()

    create_response = client.post(
        "/proposals",
        json={
            "supplier_id": supplier["id"],
            "procurement_event_id": procurement_event["id"],
        },
    )

    proposal_id = create_response.json()["id"]

    response = client.get(
        f"/proposals/{proposal_id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == proposal_id
    assert data["supplier_id"] == supplier["id"]
    assert (
        data["procurement_event_id"]
        == procurement_event["id"]
    )


def test_get_proposal_not_found():
    proposal_id = uuid.uuid4()

    response = client.get(
        f"/proposals/{proposal_id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Proposal not found"
    }


def test_create_proposal_supplier_not_found():
    procurement_event = create_procurement_event()

    response = client.post(
        "/proposals",
        json={
            "supplier_id": str(uuid.uuid4()),
            "procurement_event_id": procurement_event["id"],
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Supplier not found"
    }


def test_create_proposal_procurement_event_not_found():
    supplier = create_supplier()

    response = client.post(
        "/proposals",
        json={
            "supplier_id": supplier["id"],
            "procurement_event_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Procurement event not found"
    }


def test_proposals_requires_api_key():
    unauthenticated_client = TestClient(app)

    response = unauthenticated_client.get(
        "/proposals"
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or missing API key"
    }
