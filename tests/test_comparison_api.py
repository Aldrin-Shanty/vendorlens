
import uuid
import pytest
import httpx
from fastapi.testclient import TestClient
from vendorlens.api.main import app

from vendorlens.api.routes import comparison
from vendorlens.services.errors import (
    AIOutputError,
    AIServiceUnavailableError,
    EvidenceValidationError,
    SupplierSelectionError,
)
from vendorlens.services.schemas.supplier_comparison import (
    SupplierComparison,
    SupplierComparisonEntry,
    SupplierFacts,
)


def create_event(client):
    response = client.post(
        "/procurement-events",
        json={"title": "Laptop Procurement"},
    )

    assert response.status_code == 201
    return response.json()["id"]


def test_compare_suppliers_success(client, monkeypatch):
    event_id = create_event(client)

    dell_id = uuid.uuid4()
    hp_id = uuid.uuid4()

    def fake_compare_suppliers(
        db,
        procurement_event_id,
        supplier_ids,
    ):
        assert str(procurement_event_id) == event_id
        assert supplier_ids == [dell_id, hp_id]

        return SupplierComparison(
            procurement_event_id=procurement_event_id,
            suppliers=[
                SupplierComparisonEntry(
                    supplier_id=dell_id,
                    facts=SupplierFacts(
                        supplier_name="Dell",
                        missing_information=["Delivery timeline"],
                    ),
                    evidence={},
                ),
                SupplierComparisonEntry(
                    supplier_id=hp_id,
                    facts=SupplierFacts(
                        supplier_name="HP",
                        missing_information=["Warranty"],
                    ),
                    evidence={},
                ),
            ],
        )

    monkeypatch.setattr(
        comparison,
        "compare_suppliers",
        fake_compare_suppliers,
    )

    response = client.post(
        f"/procurement-events/{event_id}/compare",
        json={
            "supplier_ids": [
                str(dell_id),
                str(hp_id),
            ],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["procurement_event_id"] == event_id
    assert len(data["suppliers"]) == 2

    assert data["suppliers"][0]["supplier_id"] == str(dell_id)
    assert data["suppliers"][1]["supplier_id"] == str(hp_id)

    assert data["suppliers"][0]["facts"]["supplier_name"] == "Dell"
    assert data["suppliers"][1]["facts"]["supplier_name"] == "HP"

    assert data["suppliers"][0]["evidence"] == {}
    assert data["suppliers"][1]["evidence"] == {}


def test_compare_suppliers_requires_two_suppliers(client):
    event_id = create_event(client)

    response = client.post(
        f"/procurement-events/{event_id}/compare",
        json={
            "supplier_ids": [str(uuid.uuid4())],
        },
    )

    assert response.status_code == 422


def test_compare_suppliers_rejects_duplicates(client):
    event_id = create_event(client)
    supplier_id = str(uuid.uuid4())

    response = client.post(
        f"/procurement-events/{event_id}/compare",
        json={
            "supplier_ids": [
                supplier_id,
                supplier_id,
            ],
        },
    )

    assert response.status_code == 422


def test_compare_suppliers_rejects_invalid_uuid(client):
    event_id = create_event(client)

    response = client.post(
        f"/procurement-events/{event_id}/compare",
        json={
            "supplier_ids": [
                "not-a-valid-uuid",
                str(uuid.uuid4()),
            ],
        },
    )

    assert response.status_code == 422


def test_compare_suppliers_event_not_found(client):
    response = client.post(
        f"/procurement-events/{uuid.uuid4()}/compare",
        json={
            "supplier_ids": [
                str(uuid.uuid4()),
                str(uuid.uuid4()),
            ],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Procurement event not found"


def test_compare_rejects_supplier_without_proposal(
    client,
    monkeypatch,
):
    event_id = create_event(client)

    def fake_compare_suppliers(**kwargs):
        raise SupplierSelectionError(
            "Supplier has no proposal in this procurement event"
        )

    monkeypatch.setattr(
        comparison,
        "compare_suppliers",
        fake_compare_suppliers,
    )

    response = client.post(
        f"/procurement-events/{event_id}/compare",
        json={
            "supplier_ids": [
                str(uuid.uuid4()),
                str(uuid.uuid4()),
            ],
        },
    )

    assert response.status_code == 400
    assert "no proposal" in response.json()["detail"]


def test_compare_rejects_invalid_ai_evidence(
    client,
    monkeypatch,
):
    event_id = create_event(client)

    def fake_compare_suppliers(**kwargs):
        raise EvidenceValidationError(
            "Evidence 99 does not exist"
        )

    monkeypatch.setattr(
        comparison,
        "compare_suppliers",
        fake_compare_suppliers,
    )

    response = client.post(
        f"/procurement-events/{event_id}/compare",
        json={
            "supplier_ids": [
                str(uuid.uuid4()),
                str(uuid.uuid4()),
            ],
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "AI-generated supplier facts could not be validated"
    assert "Evidence 99" not in response.text

@pytest.mark.parametrize("error, status", [
    (AIOutputError("Invalid provider output"), 502),
    (AIServiceUnavailableError("Unavailable"), 503),
    (httpx.ConnectError("Connection failed"), 503),
    (httpx.ReadTimeout("Timed out"), 503),
])
def test_compare_maps_ai_errors(client, monkeypatch, error, status):
    event_id = create_event(client)

    def fake_compare(**kwargs):
        raise error

    monkeypatch.setattr(comparison, "compare_suppliers", fake_compare)
    response = client.post(
        f"/procurement-events/{event_id}/compare",
        json={"supplier_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
    )
    assert response.status_code == status
    assert str(error) not in response.json()["detail"]


def test_compare_requires_api_key():
    with TestClient(app) as unauthenticated_client:
        response = unauthenticated_client.post(
            f"/procurement-events/{uuid.uuid4()}/compare",
            json={"supplier_ids": [str(uuid.uuid4()), str(uuid.uuid4())]},
        )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_compare_rejects_supplier_budget(client):
    event_id = create_event(client)
    response = client.post(
        f"/procurement-events/{event_id}/compare",
        json={"supplier_ids": [str(uuid.uuid4()) for _ in range(9)]},
    )
    assert response.status_code == 422


def test_comparison_service_through_api_preserves_provenance(client, monkeypatch):
    from vendorlens.services import comparison as comparison_service
    from vendorlens.services.fact_extraction import SupplierExtractionResult
    from vendorlens.services.schemas.supplier_comparison import EvidenceReference, FactEvidence

    event_id = create_event(client)
    supplier_ids = []
    for name in ("Synthetic Dell", "Synthetic HP"):
        supplier_response = client.post("/suppliers", json={"name": name})
        assert supplier_response.status_code == 201
        supplier_id = supplier_response.json()["id"]
        supplier_ids.append(supplier_id)
        proposal = client.post("/proposals", json={
            "supplier_id": supplier_id, "procurement_event_id": event_id,
        })
        assert proposal.status_code == 201

    chunk_ids = {}

    def fake_extract(db, procurement_event_id, supplier_id, supplier_name):
        assert str(procurement_event_id) == event_id
        chunk_id = uuid.uuid4()
        chunk_ids[str(supplier_id)] = str(chunk_id)
        return SupplierExtractionResult(
            facts=SupplierFacts(supplier_name=supplier_name, warranty_years=3,
                                warranty_evidence=FactEvidence(evidence_ids=[2])),
            evidence={2: EvidenceReference(chunk_id=chunk_id, document_version_id=uuid.uuid4(),
                                          filename="synthetic.pdf", page_number=2, text="Warranty: 3 years.")},
        )

    monkeypatch.setattr(comparison_service, "extract_facts_for_supplier", fake_extract)
    response = client.post(f"/procurement-events/{event_id}/compare", json={"supplier_ids": supplier_ids})
    assert response.status_code == 200
    entries = response.json()["suppliers"]
    assert [entry["supplier_id"] for entry in entries] == supplier_ids
    for entry in entries:
        assert entry["facts"]["warranty_evidence"]["evidence_ids"] == [2]
        assert set(entry["evidence"]) == {"2"}
        assert entry["evidence"]["2"]["chunk_id"] == chunk_ids[entry["supplier_id"]]
        assert entry["judgment"]["status"] == "not_checked"
