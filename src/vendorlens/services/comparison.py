import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.db.models.proposal import Proposal
from vendorlens.db.models.supplier import Supplier
from vendorlens.services.fact_extraction import extract_facts_for_supplier
from vendorlens.services.schemas.supplier_comparison import SupplierComparison, SupplierComparisonEntry
from vendorlens.services.errors import SupplierSelectionError


def compare_suppliers(
    db: Session,
    procurement_event_id: uuid.UUID,
    supplier_ids: list[uuid.UUID],
) -> SupplierComparison:
    if len(supplier_ids) < 2:
        raise SupplierSelectionError("At least two suppliers are required")
    if len(supplier_ids) != len(set(supplier_ids)):
        raise SupplierSelectionError("Duplicate supplier IDs are not allowed")

    selected_suppliers = []

    for supplier_id in supplier_ids:
        statement = (
            select(Supplier.name)
            .join(Proposal, Proposal.supplier_id == Supplier.id)
            .where(
                Proposal.procurement_event_id == procurement_event_id,
                Supplier.id == supplier_id,
            )
        )

        supplier_name = db.scalar(statement)

        if supplier_name is None:
            raise SupplierSelectionError(
                f"Supplier {supplier_id} has no proposal in this procurement event"
            )

        selected_suppliers.append((supplier_id, supplier_name))

    # Validate the entire selection before making any AI calls.
    entries = []
    for supplier_id, supplier_name in selected_suppliers:
        extraction = extract_facts_for_supplier(
            db=db,
            procurement_event_id=procurement_event_id,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
        )

        entries.append(
            SupplierComparisonEntry(
                supplier_id=supplier_id,
                facts=extraction.facts,
                evidence=extraction.evidence,
            )
        )

    return SupplierComparison(
        procurement_event_id=procurement_event_id,
        suppliers=entries,
    )
