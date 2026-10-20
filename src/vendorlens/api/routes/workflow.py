from fastapi import APIRouter, Depends, HTTPException
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.orm import Session

from vendorlens.api.dependencies import get_checkpointer, get_db
from vendorlens.core.security import require_api_key
from vendorlens.services.errors import DeletionConfirmationRequired
from vendorlens.workflows.catalog import WorkflowSummary, delete_workflows, list_workflows

router = APIRouter(prefix="/comparison-workflows", tags=["comparison"], dependencies=[Depends(require_api_key)])


@router.get("", response_model=list[WorkflowSummary])
def list_all_comparison_workflows(db: Session = Depends(get_db), checkpointer: BaseCheckpointSaver = Depends(get_checkpointer)):
    return list_workflows(db, checkpointer)


@router.delete("", status_code=204)
def delete_all_comparison_workflows(confirm: bool = False, db: Session = Depends(get_db), checkpointer: BaseCheckpointSaver = Depends(get_checkpointer)):
    try:
        delete_workflows(db, checkpointer, confirmed=confirm)
    except DeletionConfirmationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
