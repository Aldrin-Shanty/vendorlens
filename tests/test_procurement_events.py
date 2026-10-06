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


def test_create_procurement_event():
    response = client.post(
        "/procurement-events",
        json={"title": "Laptop Procurement 2027"},
    )

    assert response.status_code == 201

    data = response.json()

    assert data["title"] == "Laptop Procurement 2027"
    assert "id" in data


def test_get_procurement_events():
    create_response = client.post(
        "/procurement-events",
        json={"title": "Laptop Procurement 2027"},
    )

    assert create_response.status_code == 201

    response = client.get("/procurement-events")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["title"] == "Laptop Procurement 2027"


def test_get_procurement_event():
    create_response = client.post(
        "/procurement-events",
        json={"title": "Laptop Procurement 2027"},
    )

    assert create_response.status_code == 201

    created_event = create_response.json()
    procurement_event_id = created_event["id"]

    response = client.get(
        f"/procurement-events/{procurement_event_id}"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == procurement_event_id
    assert data["title"] == "Laptop Procurement 2027"


def test_get_procurement_event_not_found():
    procurement_event_id = uuid.uuid4()

    response = client.get(
        f"/procurement-events/{procurement_event_id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Procurement event not found"
    }


def test_create_procurement_event_with_empty_title():
    response = client.post(
        "/procurement-events",
        json={"title": ""},
    )

    assert response.status_code == 422


def test_update_procurement_event():
    create_response = client.post(
        "/procurement-events",
        json={"title": "Old Procurement Event"},
    )

    procurement_event_id = create_response.json()["id"]

    response = client.put(
        f"/procurement-events/{procurement_event_id}",
        json={"title": "New Procurement Event"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == procurement_event_id
    assert data["title"] == "New Procurement Event"


def test_delete_procurement_event():
    create_response = client.post(
        "/procurement-events",
        json={"title": "Procurement Event To Delete"},
    )

    procurement_event_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/procurement-events/{procurement_event_id}"
    )

    assert delete_response.status_code == 204

    get_response = client.get(
        f"/procurement-events/{procurement_event_id}"
    )

    assert get_response.status_code == 404


def test_procurement_events_requires_api_key():
    unauthenticated_client = TestClient(app)

    response = unauthenticated_client.get(
        "/procurement-events"
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or missing API key"
    }

def test_delete_procurement_event_with_existing_proposal():
    # Create supplier
    supplier_response = client.post(
        "/suppliers",
        json={"name": "Referenced Supplier"},
    )

    assert supplier_response.status_code == 201
    supplier = supplier_response.json()

    # Create procurement event
    procurement_event_response = client.post(
        "/procurement-events",
        json={"title": "Referenced Procurement Event"},
    )

    assert procurement_event_response.status_code == 201
    procurement_event = procurement_event_response.json()

    # Create proposal connecting the supplier and event
    proposal_response = client.post(
        "/proposals",
        json={
            "supplier_id": supplier["id"],
            "procurement_event_id": procurement_event["id"],
        },
    )

    assert proposal_response.status_code == 201

    # Procurement event is referenced by the proposal,
    # so deletion should be rejected.
    response = client.delete(
        f"/procurement-events/{procurement_event['id']}"
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Procurement event cannot be deleted because "
            "it has existing proposals"
        )
    }
