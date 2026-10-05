import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.api.dependencies import get_db
from vendorlens.api.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate
from vendorlens.db.models.supplier import Supplier
from vendorlens.core.security import require_api_key

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
):
    statement = select(Supplier).where(Supplier.id == supplier_id)
    supplier = db.scalars(statement).first()

    if supplier is None:
        raise HTTPException(
            status_code=404,
            detail="Supplier not found",
        )

    db.delete(supplier)
    db.commit()
