import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.api.dependencies import get_db
from vendorlens.api.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from vendorlens.db.models.supplier import Supplier
from vendorlens.core.security import require_api_key
from vendorlens.api.storage_dependencies import get_storage
from vendorlens.api.deletion import perform_deletion
from vendorlens.services.deletion import DeletionImpact, get_deletion_impact
from vendorlens.services.storage import LocalFileStorage
from vendorlens.services.data_locks import lock_records

router = APIRouter(
    prefix="/suppliers",
    tags=["suppliers"],
    dependencies=[Depends(require_api_key)],
)

@router.post("", response_model=SupplierRead, status_code=201)
def create_supplier(
    supplier_data: SupplierCreate,
    db: Session = Depends(get_db),
):
    supplier = Supplier(name=supplier_data.name)

    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    return supplier

@router.get("", response_model=list[SupplierRead])
def get_suppliers(
    db: Session = Depends(get_db),
):
    statement = select(Supplier)

    suppliers = db.scalars(statement).all()

    return suppliers

@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(
    supplier_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    statement = select(Supplier).where(Supplier.id == supplier_id)

    supplier = db.scalars(statement).first()

    if supplier is None:
        raise HTTPException(
            status_code=404,
                detail="Supplier not found",
        )

    return supplier

@router.put("/{supplier_id}", response_model=SupplierRead)
def update_supplier(
    supplier_id: uuid.UUID,
    supplier_data: SupplierUpdate,
    db: Session = Depends(get_db),
):
    statement = select(Supplier).where(Supplier.id == supplier_id)
    supplier = db.scalars(statement).first()

    if supplier is None:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found",
        )

    supplier.name = supplier_data.name

    db.commit()
    db.refresh(supplier)

    return supplier

@router.delete("/{supplier_id}", status_code=204)
def delete_supplier(
    supplier_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: LocalFileStorage = Depends(get_storage),
    confirm_related: bool = False,
):
    lock_records(db, [f"supplier:{supplier_id}"], shared=False)
    statement = select(Supplier).where(Supplier.id == supplier_id).with_for_update()
    supplier = db.scalars(statement).first()

    if supplier is None:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found",
        )

    perform_deletion(db, supplier, storage, confirm_related)


@router.get("/{supplier_id}/deletion-impact", response_model=DeletionImpact)
def preview_supplier_deletion(supplier_id: uuid.UUID, db: Session = Depends(get_db)):
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return get_deletion_impact(db, supplier)
