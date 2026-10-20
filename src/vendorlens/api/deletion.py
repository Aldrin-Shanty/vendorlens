from fastapi import HTTPException
from sqlalchemy.orm import Session

from vendorlens.services.deletion import DeletionTarget, delete_record
from vendorlens.services.errors import DeletionConfirmationRequired, DeletionStorageError
from vendorlens.services.storage import LocalFileStorage


def perform_deletion(db: Session, target: DeletionTarget, storage: LocalFileStorage, confirm_related: bool) -> None:
    try:
        delete_record(db, target, storage, confirm_related=confirm_related)
    except DeletionConfirmationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DeletionStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
