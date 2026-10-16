import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from vendorlens.db.models.proposal import Proposal
from vendorlens.db.models.supplier import Supplier
from vendorlens.services.fact_extraction import retrieve_supplier_evidence, extract_facts_from_evidence, validate_supplier_facts, build_evidence_references
from vendorlens.services.schemas.supplier_comparison import SupplierComparison, SupplierComparisonEntry
from vendorlens.services.errors import SupplierSelectionError
from vendorlens.services.evidence_judgment import judge_supplier_facts


def validate_supplier_selection(
    db: Session,
    procurement_event_id: uuid.UUID,
    supplier_ids: list[uuid.UUID],
) -> list[tuple[uuid.UUID, str]]:
    if len(supplier_ids) < 2:
        raise SupplierSelectionError("At least two suppliers are required")
    if len(supplier_ids) > 8:
        raise SupplierSelectionError("At most eight suppliers can be compared")
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

    return selected_suppliers


def compare_suppliers(
    db: Session,
    procurement_event_id: uuid.UUID,
    supplier_ids: list[uuid.UUID],
) -> SupplierComparison:
    """Run the comparison workflow in business order, like document ingestion."""
    selected_suppliers = validate_supplier_selection(db, procurement_event_id, supplier_ids)

    entries = []
    for supplier_id, supplier_name in selected_suppliers:
        sources = retrieve_supplier_evidence(db, procurement_event_id, supplier_id)
        facts = extract_facts_from_evidence(supplier_name, sources)
        validate_supplier_facts(facts, supplier_id, supplier_name, sources)
        evidence = build_evidence_references(facts, sources)
        judgment = judge_supplier_facts(facts, evidence)

        entries.append(
            SupplierComparisonEntry(
                supplier_id=supplier_id,
                facts=facts,
                evidence=evidence,
                judgment=judgment,
            )
        )

    return SupplierComparison(
        procurement_event_id=procurement_event_id,
        suppliers=entries,
    )
