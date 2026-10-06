from json import load
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


def test_duplicate_document_upload(temp_storage):
    supplier_response = client.post(
        "/suppliers",
        json={"name": "Dell"},
    )

    assert supplier_response.status_code == 201

    supplier = supplier_response.json()

    event_response = client.post(
        "/procurement-events",
        json={"title": "Laptop Procurement 2027"},
    )

    assert event_response.status_code == 201

    event = event_response.json()

    proposal_response = client.post(
        "/proposals",
        json={
            "supplier_id": supplier["id"],
            "procurement_event_id": event["id"],
        },
    )

    assert proposal_response.status_code == 201

    proposal = proposal_response.json()

    pdf_bytes = b"%PDF-1.4 fake test pdf"

    files = {
        "file": (
            "proposal.pdf",
            pdf_bytes,
            "application/pdf",
        )
    }

    first_response = client.post(
        f"/proposals/{proposal['id']}/documents",
        files=files,
    )

    assert first_response.status_code == 201

    second_response = client.post(
        f"/proposals/{proposal['id']}/documents",
        files=files,
    )

    assert second_response.status_code == 409

    assert second_response.json() == {
        "detail": "This file has already been uploaded for this proposal"
    }

def create_proposal():
    supplier_response = client.post(
        "/suppliers",
        json={"name": "Test Supplier"},
    )
    assert supplier_response.status_code == 201

    event_response = client.post(
        "/procurement-events",
        json={"title": "Test Procurement"},
    )
    assert event_response.status_code == 201

    proposal_response = client.post(
        "/proposals",
        json={
            "supplier_id": supplier_response.json()["id"],
            "procurement_event_id": event_response.json()["id"],
        },
    )

    assert proposal_response.status_code == 201

    return proposal_response.json()

def test_upload_unsupported_document_type(temp_storage):
    proposal = create_proposal()

    response = client.post(
        f"/proposals/{proposal['id']}/documents",
        files={
            "file": (
                "notes.txt",
                b"hello",
                "text/plain",
            )
        },
    )

    assert response.status_code == 415
    assert response.json() == {
        "detail": "Unsupported file type"
    }

def test_upload_document_to_missing_proposal(temp_storage):
    missing_proposal_id = (
        "00000000-0000-0000-0000-000000000001"
    )

    response = client.post(
        f"/proposals/{missing_proposal_id}/documents",
        files={
            "file": (
                "proposal.pdf",
                b"%PDF-1.4 fake pdf",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Proposal not found"
    }
