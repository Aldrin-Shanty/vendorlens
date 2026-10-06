import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.api.storage_dependencies import get_storage
from vendorlens.services.storage import LocalFileStorage
from vendorlens.api.dependencies import get_db
from vendorlens.db.models.document import Document
from vendorlens.db.models.document_version import DocumentVersion
from vendorlens.db.models.proposal import Proposal
from vendorlens.core.security import require_api_key
from vendorlens.services.ingestion import ingest_document_version

router = APIRouter(
    prefix="/proposals/{proposal_id}/documents",
    tags=["documents"],
    dependencies=[Depends(require_api_key)],
)

CHUNK_SIZE = 1024 * 1024  # 1 MiB

MAX_FILE_SIZE = 10 * 1024 * 1024 # 10 MiB

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
}


@router.post("", status_code=201)
async def upload_document(
    proposal_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: LocalFileStorage = Depends(get_storage),
):
    proposal_statement = select(Proposal).where(
        Proposal.id == proposal_id
    )
    proposal = db.scalars(proposal_statement).first()

    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail="Proposal not found",
        )

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type",
        )

    hasher = hashlib.sha256()
    size = 0

    storage_key = f"{uuid.uuid4()}.pdf"

    try:
        while chunk := await file.read(CHUNK_SIZE):
            size += len(chunk)

            if size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail="File is too large",
                )

            hasher.update(chunk)

            storage.write_chunk(
                storage_key,
                chunk,
            )

    except Exception:
        storage.delete(storage_key)
        raise

    sha256 = hasher.hexdigest()

    duplicate_statement = (
        select(DocumentVersion)
        .join(Document)
        .where(
            Document.proposal_id == proposal_id,
            DocumentVersion.sha256 == sha256,
        )
    )

    existing_version = db.scalars(
        duplicate_statement
    ).first()

    if existing_version is not None:
        storage.delete(storage_key)

        raise HTTPException(
            status_code=409,
            detail="This file has already been uploaded for this proposal",
    )
    try:
        document = Document(
            proposal_id=proposal.id,
        )

        db.add(document)
        db.flush()

        document_version = DocumentVersion(
            document_id=document.id,
            filename=file.filename or "unknown.pdf",
            content_type=file.content_type,
            sha256=sha256,
            storage_key=storage_key,
        )

        db.add(document_version)
        db.flush()

        ingest_document_version(
        db=db,
        document_version=document_version,
        path=storage.get_path(storage_key),
        )

        db.commit()

    except Exception:
        db.rollback()
        storage.delete(storage_key)
        raise

    return {
        "document_id": document.id,
        "version_id": document_version.id,
        "filename": document_version.filename,
        "content_type": document_version.content_type,
        "sha256": document_version.sha256,
    }
