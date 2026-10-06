from fastapi.testclient import TestClient

from vendorlens.api.main import app


client = TestClient(app)

HEADERS = {
    "X-API-Key": "dev-secret-key",
}


def test_duplicate_document_upload():
    # Create supplier
    supplier_response = client.post(
        "/suppliers",
        json={"name": "Dell"},
        headers=HEADERS,
    )

    assert supplier_response.status_code == 201

    supplier = supplier_response.json()

    # Create procurement event
    event_response = client.post(
        "/procurement-events",
        json={"title": "Laptop Procurement 2027"},
        headers=HEADERS,
    )

    assert event_response.status_code == 201

    event = event_response.json()

    # Create proposal connecting the supplier and event
    proposal_response = client.post(
        "/proposals",
        json={
            "supplier_id": supplier["id"],
            "procurement_event_id": event["id"],
        },
        headers=HEADERS,
    )

    assert proposal_response.status_code == 201

    proposal = proposal_response.json()

    # Fake PDF bytes are enough for this test because we're testing
    # upload/deduplication, not PDF parsing yet.
    pdf_bytes = b"%PDF-1.4 fake test pdf"

    files = {
        "file": (
            "proposal.pdf",
            pdf_bytes,
            "application/pdf",
        )
    }

    # First upload should succeed.
    first_response = client.post(
        f"/proposals/{proposal['id']}/documents",
        files=files,
        headers=HEADERS,
    )

    assert first_response.status_code == 201

    # Upload the exact same bytes again.
    second_response = client.post(
        f"/proposals/{proposal['id']}/documents",
        files=files,
        headers=HEADERS,
    )

    # Same SHA-256 + same proposal should be considered a duplicate.
    assert second_response.status_code == 409

    assert second_response.json() == {
        "detail": "This file has already been uploaded for this proposal"
    }
