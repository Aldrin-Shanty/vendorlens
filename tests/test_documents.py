import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import select

from vendorlens.api.main import app
from vendorlens.db.models.chunk import Chunk
from vendorlens.services.retrieval import semantic_search

load_dotenv()

API_KEY = os.getenv("API_KEY")

if API_KEY is None:
    raise RuntimeError("API_KEY environment variable is not set")


client = TestClient(
    app,
    headers={"X-API-Key": API_KEY},
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PDF = FIXTURES_DIR / "sample_proposal.pdf"

def sample_pdf_bytes() -> bytes:
    return SAMPLE_PDF.read_bytes()

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

    pdf_bytes = sample_pdf_bytes()

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
                sample_pdf_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Proposal not found"
    }

def test_upload_document_creates_chunks(
    temp_storage,
    db,
):
    proposal = create_proposal()

    response = client.post(
        f"/proposals/{proposal['id']}/documents",
        files={
            "file": (
                "proposal.pdf",
                sample_pdf_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201

    chunks = db.scalars(
        select(Chunk).order_by(Chunk.chunk_index)
    ).all()

    assert len(chunks) > 0

    first_chunk = chunks[0]

    assert first_chunk.page_number == 1
    assert first_chunk.chunk_index == 0
    assert "warranty period is three years" in first_chunk.text

    assert chunks[0].embedding is not None
    assert len(chunks[0].embedding) == 384

def test_semantic_search_finds_warranty_chunk(db, temp_storage):
    proposal = create_proposal()

    with SAMPLE_PDF.open("rb") as pdf:
        response = client.post(
            f"/proposals/{proposal['id']}/documents",
            files={
                "file": (
                    "sample_proposal.pdf",
                    pdf,
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 201

    results = semantic_search(
        db,
        procurement_event_id=proposal["procurement_event_id"],
        query="How long is the supplier warranty?",
        limit=1,
    )

    assert len(results) == 1

    result = results[0]

    assert result.supplier_name == "Test Supplier"
    assert result.filename == "sample_proposal.pdf"
    assert result.page_number == 1
    assert "warranty" in result.text.lower()
    assert result.distance >= 0

def test_search_procurement_event_api(temp_storage):
    proposal = create_proposal()

    with SAMPLE_PDF.open("rb") as pdf:
        upload_response = client.post(
            f"/proposals/{proposal['id']}/documents",
            files={
                "file": (
                    "sample_proposal.pdf",
                    pdf,
                    "application/pdf",
                )
            },
        )

    assert upload_response.status_code == 201

    response = client.post(
        f"/procurement-events/{proposal['procurement_event_id']}/search",
        json={
            "query": "How long is the warranty?",
            "limit": 1,
        },
    )

    assert response.status_code == 200

    results = response.json()

    assert len(results) == 1
    assert results[0]["supplier_name"] == "Test Supplier"
    assert results[0]["page_number"] == 1
    assert "warranty" in results[0]["text"].lower()

def test_ask_procurement_event_api(
    temp_storage,
    monkeypatch,
):
    proposal = create_proposal()

    with SAMPLE_PDF.open("rb") as pdf:
        upload_response = client.post(
            f"/proposals/{proposal['id']}/documents",
            files={
                "file": (
                    "sample_proposal.pdf",
                    pdf,
                    "application/pdf",
                )
            },
        )

    assert upload_response.status_code == 201

    def fake_generate_answer(prompt: str) -> str:
        assert "three years" in prompt.lower()
        return "The laptop warranty is three years [Evidence 1]."

    monkeypatch.setattr(
        "vendorlens.services.rag.generate_answer",
        fake_generate_answer,
    )

    response = client.post(
        f"/procurement-events/{proposal['procurement_event_id']}/ask",
        json={
            "question": "How long is the laptop warranty?"
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["answer"] == (
        "The laptop warranty is three years [Evidence 1]."
    )

    assert len(body["retrieved_evidence"]) >= 1

    evidence = body["retrieved_evidence"][0]

    assert evidence["supplier_name"] == "Test Supplier"
    assert evidence["filename"] == "sample_proposal.pdf"
    assert evidence["page_number"] == 1
    assert "warranty" in evidence["text"].lower()
