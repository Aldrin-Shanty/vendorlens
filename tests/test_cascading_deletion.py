import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vendorlens.api.main import app
from vendorlens.db.models.chunk import Chunk
from vendorlens.db.models.document import Document
from vendorlens.db.models.document_version import DocumentVersion
from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.db.models.proposal import Proposal
from vendorlens.db.models.supplier import Supplier
from vendorlens.workflows.checkpoint import initialize_checkpoints, open_checkpointer


@pytest.fixture
def records(db, temp_storage):
    suppliers = [Supplier(name=f"Supplier {i}") for i in range(2)]
    events = [ProcurementEvent(title=f"Event {i}") for i in range(2)]
    db.add_all([*suppliers, *events])
    db.flush()
    proposals = []
    files = {}
    for supplier in suppliers:
        for event in events:
            proposal = Proposal(supplier_id=supplier.id, procurement_event_id=event.id)
            db.add(proposal)
            db.flush()
            proposals.append(proposal)
            keys = []
            for _ in range(2):
                document = Document(proposal_id=proposal.id)
                db.add(document)
                db.flush()
                for _ in range(2):
                    key = f"{uuid.uuid4()}.pdf"
                    version = DocumentVersion(document_id=document.id, filename="test.pdf", content_type="application/pdf", sha256=uuid.uuid4().hex * 2, storage_key=key)
                    db.add(version)
                    db.flush()
                    db.add_all([Chunk(document_version_id=version.id, page_number=1, chunk_index=i, text="Synthetic evidence") for i in range(2)])
                    temp_storage.write_chunk(key, b"synthetic stored PDF bytes")
                    keys.append(key)
            files[proposal.id] = keys
    db.commit()
    return suppliers, events, proposals, files


def target_for(kind, records):
    suppliers, events, proposals, _ = records
    if kind == "proposals":
        return proposals[0], [proposals[0].id]
    if kind == "suppliers":
        return suppliers[0], [p.id for p in proposals if p.supplier_id == suppliers[0].id]
    return events[0], [p.id for p in proposals if p.procurement_event_id == events[0].id]


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


@pytest.mark.parametrize("kind", ["proposals", "procurement-events", "suppliers"])
def test_preview_and_confirmed_delete_remove_only_owned_data(client, db, temp_storage, records, kind):
    suppliers, events, proposals, files = records
    target, deleted = target_for(kind, records)
    target_id = target.id
    preview = client.get(f"/{kind}/{target_id}/deletion-impact")
    assert preview.status_code == 200
    assert preview.json() == {
        "proposals": 0 if kind == "proposals" else len(deleted),
        "documents": len(deleted) * 2,
        "document_versions": len(deleted) * 4,
        "evidence_chunks": len(deleted) * 8,
        "comparison_workflows": 0,
        "comparison_workflow_ids": [],
    }

    unconfirmed = client.delete(f"/{kind}/{target_id}")
    assert unconfirmed.status_code == 409
    assert count(db, Proposal) == 4
    assert all(temp_storage.get_path(key).exists() for keys in files.values() for key in keys)

    confirmed = client.delete(f"/{kind}/{target_id}?confirm_related=true")
    assert confirmed.status_code == 204
    assert confirmed.content == b""
    db.expire_all()
    assert db.get(type(target), target_id) is None
    assert count(db, Proposal) == 4 - len(deleted)
    assert count(db, Document) == (4 - len(deleted)) * 2
    assert count(db, DocumentVersion) == (4 - len(deleted)) * 4
    assert count(db, Chunk) == (4 - len(deleted)) * 8
    assert count(db, Supplier) == (1 if kind == "suppliers" else 2)
    assert count(db, ProcurementEvent) == (1 if kind == "procurement-events" else 2)
    for proposal_id, keys in files.items():
        for key in keys:
            assert temp_storage.get_path(key).exists() == (proposal_id not in deleted)


@pytest.mark.parametrize("kind, model, values", [
    ("suppliers", Supplier, {"name": "Empty supplier"}),
    ("procurement-events", ProcurementEvent, {"title": "Empty event"}),
])
def test_empty_parent_needs_no_related_data_confirmation(client, db, kind, model, values):
    target = model(**values)
    db.add(target)
    db.commit()
    response = client.get(f"/{kind}/{target.id}/deletion-impact")
    assert response.status_code == 200
    assert all(value == 0 for key, value in response.json().items() if key != "comparison_workflow_ids")
    assert client.delete(f"/{kind}/{target.id}").status_code == 204


def test_file_staging_failure_preserves_all_records_and_files(client, db, temp_storage, records, monkeypatch):
    target = records[2][0]
    original_replace = Path.replace
    attempts = 0

    def fail_second_file(source, destination):
        nonlocal attempts
        if source.parent == temp_storage.root.resolve():
            attempts += 1
            if attempts == 2:
                raise PermissionError("Synthetic locked PDF")
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", fail_second_file)
    response = client.delete(f"/proposals/{target.id}?confirm_related=true")
    assert response.status_code == 503
    assert "Nothing was deleted" in response.json()["detail"]
    assert count(db, Proposal) == 4
    assert count(db, Chunk) == 32
    assert all(temp_storage.get_path(key).exists() for keys in records[3].values() for key in keys)


def test_database_failure_restores_staged_files(client, db, temp_storage, records, monkeypatch):
    def fail_commit(self):
        raise RuntimeError("Synthetic database commit failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="Synthetic database commit failure"):
        client.delete(f"/proposals/{records[2][0].id}?confirm_related=true")
    assert count(db, Proposal) == 4
    assert count(db, DocumentVersion) == 16
    assert count(db, Chunk) == 32
    assert all(temp_storage.get_path(key).exists() for keys in records[3].values() for key in keys)


def test_missing_pdf_does_not_prevent_deleting_remaining_evidence(client, db, temp_storage, records):
    target = records[2][0]
    temp_storage.get_path(records[3][target.id][0]).unlink()
    response = client.delete(f"/proposals/{target.id}?confirm_related=true")
    assert response.status_code == 204
    assert count(db, Proposal) == 3
    assert all(not temp_storage.get_path(key).exists() for key in records[3][target.id])


def test_final_cleanup_failure_reports_that_the_record_was_deleted(client, db, temp_storage, records, monkeypatch):
    original_unlink = Path.unlink

    def fail_staged_cleanup(path, *args, **kwargs):
        if path.parent.parent.name == ".deletions":
            raise PermissionError("Synthetic cleanup failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_staged_cleanup)
    response = client.delete(f"/proposals/{records[2][0].id}?confirm_related=true")
    assert response.status_code == 503
    assert "were deleted" in response.json()["detail"]
    assert "cleanup could not finish" in response.json()["detail"]
    assert count(db, Proposal) == 3
    assert count(db, Chunk) == 24


def test_comparison_locks_block_deletion_until_transaction_ends(db):
    from sqlalchemy import text
    from vendorlens.services.data_locks import lock_comparison_data

    event_id, supplier_id = uuid.uuid4(), uuid.uuid4()
    lock_comparison_data(db, event_id, [supplier_id])
    with Session(db.get_bind()) as contender:
        for key in (f"event:{event_id}", f"supplier:{supplier_id}"):
            statement = text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))")
            assert contender.scalar(statement, {"key": key}) is False
        db.rollback()
        for key in (f"event:{event_id}", f"supplier:{supplier_id}"):
            assert contender.scalar(statement, {"key": key}) is True


@pytest.mark.parametrize("kind", ["proposals", "procurement-events", "suppliers"])
def test_delete_and_preview_missing_record_return_404(client, kind):
    path = f"/{kind}/{uuid.uuid4()}"
    assert client.get(f"{path}/deletion-impact").status_code == 404
    assert client.delete(f"{path}?confirm_related=true").status_code == 404


@pytest.mark.parametrize("kind", ["proposals", "procurement-events", "suppliers"])
def test_delete_and_preview_require_api_key(kind):
    with TestClient(app) as client:
        path = f"/{kind}/{uuid.uuid4()}"
        assert client.get(f"{path}/deletion-impact").status_code == 401
        assert client.delete(f"{path}?confirm_related=true").status_code == 401


@pytest.mark.parametrize("kind", ["proposals", "procurement-events", "suppliers"])
@pytest.mark.parametrize("commit_fails", [False, True])
def test_related_saved_workflows_are_removed_in_same_transaction(client, db, temp_storage, records, kind, commit_fails, monkeypatch):
    import os
    from vendorlens.workflows.comparison import build_comparison_graph
    from vendorlens.workflows.budget import ExecutionBudget
    from vendorlens.workflows.state import create_initial_state
    from unittest.mock import Mock

    url = os.environ["TEST_DATABASE_URL"]
    initialize_checkpoints(url)
    target, _ = target_for(kind, records)
    suppliers, events, _, _ = records
    removed_id, kept_id = str(uuid.uuid4()), str(uuid.uuid4())
    with open_checkpointer(url) as saver:
        # Seed states without executing retrieval or any models.
        graph = build_comparison_graph(Mock(spec=Session), checkpointer=saver)
        graph.update_state({"configurable": {"thread_id": removed_id}}, create_initial_state(events[0].id, [suppliers[0].id], ExecutionBudget()))
        graph.update_state({"configurable": {"thread_id": kept_id}}, create_initial_state(events[1].id, [suppliers[1].id], ExecutionBudget()))
        try:
            preview = client.get(f"/{kind}/{target.id}/deletion-impact")
            assert preview.status_code == 200
            assert preview.json()["comparison_workflow_ids"] == [removed_id]
            if commit_fails:
                def fail_commit(self):
                    raise RuntimeError("Synthetic commit failure")
                monkeypatch.setattr(Session, "commit", fail_commit)
                with pytest.raises(RuntimeError, match="Synthetic commit failure"):
                    client.delete(f"/{kind}/{target.id}?confirm_related=true")
                assert saver.get_tuple({"configurable": {"thread_id": removed_id}}) is not None
                assert count(db, Proposal) == 4
                assert all(temp_storage.get_path(key).exists() for keys in records[3].values() for key in keys)
            else:
                response = client.delete(f"/{kind}/{target.id}?confirm_related=true")
                assert response.status_code == 204
                assert saver.get_tuple({"configurable": {"thread_id": removed_id}}) is None
            assert saver.get_tuple({"configurable": {"thread_id": kept_id}}) is not None
        finally:
            saver.delete_thread(removed_id)
            saver.delete_thread(kept_id)
