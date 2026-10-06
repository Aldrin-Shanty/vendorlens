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

def test_create_supplier():
    response = client.post(
        "/suppliers",
        json={"name": "Test Supplier"},
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "Test Supplier"
    assert "id" in data

def test_get_suppliers():
    create_response = client.post(
        "/suppliers",
        json={"name": "Acme Test"},
    )

    assert create_response.status_code == 201

    response = client.get("/suppliers")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["name"] == "Acme Test"

def test_get_supplier():
    create_response = client.post(
        "/suppliers",
        json={"name": "Specific Supplier"},
    )

    assert create_response.status_code == 201

    created_supplier = create_response.json()
    supplier_id = created_supplier["id"]

    response = client.get(f"/suppliers/{supplier_id}")

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == supplier_id
    assert data["name"] == "Specific Supplier"

def test_get_supplier_not_found():
    supplier_id = uuid.uuid4()

    response = client.get(f"/suppliers/{supplier_id}")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Supplier not found"
    }

def test_create_supplier_with_empty_name():
    response = client.post(
        "/suppliers",
        json={"name": ""},
    )

    assert response.status_code == 422

def test_update_supplier():
    create_response = client.post(
        "/suppliers",
        json={"name": "Old Name"},
    )
    supplier_id = create_response.json()["id"]

    response = client.put(
        f"/suppliers/{supplier_id}",
        json={"name": "New Name"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == supplier_id
    assert data["name"] == "New Name"


def test_delete_supplier():
    create_response = client.post(
        "/suppliers",
        json={"name": "Supplier To Delete"},
    )
    supplier_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/suppliers/{supplier_id}"
    )

    assert delete_response.status_code == 204

    get_response = client.get(
        f"/suppliers/{supplier_id}"
    )

    assert get_response.status_code == 404

def test_suppliers_requires_api_key():
    unauthenticated_client = TestClient(app)

    response = unauthenticated_client.get("/suppliers")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Invalid or missing API key"
    }

def test_delete_supplier_with_existing_proposal():
    supplier_response = client.post(
        "/suppliers",
        json={"name": "Referenced Supplier"},
    )

    assert supplier_response.status_code == 201
    supplier = supplier_response.json()

    procurement_event_response = client.post(
        "/procurement-events",
        json={"title": "Laptop Procurement 2027"},
    )

    assert procurement_event_response.status_code == 201
    procurement_event = procurement_event_response.json()

    proposal_response = client.post(
        "/proposals",
        json={
            "supplier_id": supplier["id"],
            "procurement_event_id": procurement_event["id"],
        },
    )

    assert proposal_response.status_code == 201

    response = client.delete(
        f"/suppliers/{supplier['id']}"
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": (
            "Supplier cannot be deleted because it has existing proposals"
        )
    }
