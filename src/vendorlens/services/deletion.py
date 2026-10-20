"""Delete a record and its owned evidence without deleting shared parents."""

import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from vendorlens.db.models.chunk import Chunk
from vendorlens.db.models.document import Document
from vendorlens.db.models.document_version import DocumentVersion
from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.db.models.proposal import Proposal
from vendorlens.db.models.supplier import Supplier
from vendorlens.services.data_locks import lock_records
from vendorlens.services.errors import (
    DeletionConfirmationRequired,
    DeletionStorageError,
)
from vendorlens.services.storage import LocalFileStorage
from vendorlens.workflows.checkpoint import (
    delete_comparison_threads,
    related_comparison_threads,
)

DeletionTarget = Proposal | ProcurementEvent | Supplier
logger = logging.getLogger(__name__)


class DeletionImpact(BaseModel):
    proposals: int = 0
    documents: int = 0
    document_versions: int = 0
    evidence_chunks: int = 0
    comparison_workflows: int = 0
    comparison_workflow_ids: list[str] = Field(default_factory=list)

    @property
    def has_related_data(self) -> bool:
        return any(self.model_dump().values())


def proposal_scope(target: DeletionTarget) -> Select[uuid.UUID]:
    if isinstance(target, Proposal):
        return select(Proposal.id).where(Proposal.id == target.id)
    if isinstance(target, ProcurementEvent):
        return select(Proposal.id).where(Proposal.procurement_event_id == target.id)
    return select(Proposal.id).where(Proposal.supplier_id == target.id)


def affected_threads(db: Session, target: DeletionTarget) -> list[str]:
    event_id = None
    supplier_id = None
    if isinstance(target, ProcurementEvent):
        event_id = target.id
    elif isinstance(target, Supplier):
        supplier_id = target.id
    else:
        event_id = target.procurement_event_id
        supplier_id = target.supplier_id
    return related_comparison_threads(
        db,
        procurement_event_id=event_id,
        supplier_id=supplier_id,
    )


def get_deletion_impact(db: Session, target: DeletionTarget) -> DeletionImpact:
    proposals = proposal_scope(target)
    documents = select(Document.id).where(Document.proposal_id.in_(proposals))
    versions = select(DocumentVersion.id).where(
        DocumentVersion.document_id.in_(documents)
    )
    threads = affected_threads(db, target)
    return DeletionImpact(
        proposals=0 if isinstance(target, Proposal) else db.scalar(
            select(func.count()).select_from(Proposal).where(Proposal.id.in_(proposals))
        ) or 0,
        documents=db.scalar(
            select(func.count()).select_from(Document).where(Document.id.in_(documents))
        ) or 0,
        document_versions=db.scalar(
            select(func.count()).select_from(DocumentVersion).where(DocumentVersion.id.in_(versions))
        ) or 0,
        evidence_chunks=db.scalar(
            select(func.count()).select_from(Chunk).where(Chunk.document_version_id.in_(versions))
        ) or 0,
        comparison_workflows=len(threads),
        comparison_workflow_ids=threads,
    )


@contextmanager
def stage_files(
    storage: LocalFileStorage, keys: list[str]
) -> Generator[None, None, None]:
    """Keep files in a reversible staging directory until the DB commit succeeds."""
    if not keys:
        yield
        return
    root = storage.root.resolve()
    staging = root / ".deletions" / str(uuid.uuid4())
    moved: list[tuple[Path, Path]] = []
    try:
        staging.mkdir(parents=True)
        for index, key in enumerate(dict.fromkeys(keys)):
            source = storage.get_path(key).resolve()
            if not source.is_relative_to(root):
                raise ValueError("Stored PDF path is outside the upload directory")
            if source.exists():
                destination = staging / str(index)
                source.replace(destination)
                moved.append((source, destination))
    except (OSError, ValueError) as exc:
        for source, destination in reversed(moved):
            destination.replace(source)
        if staging.exists():
            staging.rmdir()
        raise DeletionStorageError(
            "Could not prepare the PDFs for deletion. Nothing was deleted."
        ) from exc
    try:
        yield
    except BaseException:
        for source, destination in reversed(moved):
            destination.replace(source)
        staging.rmdir()
        raise
    else:
        try:
            for _, destination in moved:
                destination.unlink()
            staging.rmdir()
        except OSError as exc:
            logger.exception(
                "Record deletion committed; PDF cleanup remains in %s", staging
            )
            raise DeletionStorageError(
                "The record and database evidence were deleted, but stored PDF "
                "cleanup could not finish. Refresh your workspace and check the backend logs."
            ) from exc


def delete_record(
    db: Session,
    target: DeletionTarget,
    storage: LocalFileStorage,
    *,
    confirm_related: bool,
) -> None:
    if isinstance(target, Supplier):
        key = f"supplier:{target.id}"
    elif isinstance(target, ProcurementEvent):
        key = f"event:{target.id}"
    else:
        key = f"event:{target.procurement_event_id}"
    lock_records(db, [key], shared=False)
    # Block new children while we count, stage files, and remove their parents.
    proposals = proposal_scope(target)
    documents = select(Document.id).where(Document.proposal_id.in_(proposals))
    versions = select(DocumentVersion.id).where(
        DocumentVersion.document_id.in_(documents)
    )
    db.execute(
        select(Proposal.id).where(Proposal.id.in_(proposals)).with_for_update()
    ).all()
    db.execute(
        select(Document.id).where(Document.id.in_(documents)).with_for_update()
    ).all()
    db.execute(
        select(DocumentVersion.id).where(DocumentVersion.id.in_(versions)).with_for_update()
    ).all()
    impact = get_deletion_impact(db, target)
    if impact.has_related_data and not confirm_related:
        raise DeletionConfirmationRequired(
            "This record has related proposals, documents, evidence, or saved "
            "comparisons. Review the deletion details and confirm again."
        )

    keys = list(db.scalars(
        select(DocumentVersion.storage_key).where(DocumentVersion.id.in_(versions))
    ))
    try:
        with stage_files(storage, keys):
            delete_comparison_threads(db, impact.comparison_workflow_ids)
            db.execute(
                delete(Chunk).where(Chunk.document_version_id.in_(versions)),
                execution_options={"synchronize_session": False},
            )
            db.execute(
                delete(DocumentVersion).where(DocumentVersion.id.in_(versions)),
                execution_options={"synchronize_session": False},
            )
            db.execute(
                delete(Document).where(Document.id.in_(documents)),
                execution_options={"synchronize_session": False},
            )
            if not isinstance(target, Proposal):
                db.execute(
                    delete(Proposal).where(Proposal.id.in_(proposals)),
                    execution_options={"synchronize_session": False},
                )
            db.execute(
                delete(type(target)).where(type(target).id == target.id),
                execution_options={"synchronize_session": False},
            )
            db.commit()
    except Exception:
        db.rollback()
        raise
