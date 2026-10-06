from sqlalchemy import select

from vendorlens.db.models.procurement_event import ProcurementEvent
from vendorlens.db.models.proposal import Proposal
from vendorlens.db.models.supplier import Supplier
from vendorlens.db.models.document import Document
from vendorlens.db.models.document_version import DocumentVersion

def test_proposal_relationships(db):
    supplier = Supplier(
        name="Dell",
    )

    procurement_event = ProcurementEvent(
        title="Laptop Procurement 2027",
    )

    db.add_all([
        supplier,
        procurement_event,
    ])
    db.commit()

    proposal = Proposal(
        supplier_id=supplier.id,
        procurement_event_id=procurement_event.id,
    )

    db.add(proposal)
    db.commit()

    statement = select(Proposal).where(
        Proposal.id == proposal.id
    )

    saved_proposal = db.scalars(statement).first()

    assert saved_proposal is not None

    assert saved_proposal.supplier.id == supplier.id
    assert saved_proposal.supplier.name == "Dell"

    assert (
        saved_proposal.procurement_event.id
        == procurement_event.id
    )
    assert (
        saved_proposal.procurement_event.title
        == "Laptop Procurement 2027"
    )

    assert len(supplier.proposals) == 1
    assert supplier.proposals[0].id == proposal.id

    assert len(procurement_event.proposals) == 1
    assert procurement_event.proposals[0].id == proposal.id

def test_document_relationships(db):
    supplier = Supplier(
        name="Dell",
    )

    procurement_event = ProcurementEvent(
        title="Laptop Procurement 2027",
    )

    db.add_all([
        supplier,
        procurement_event,
    ])
    db.commit()

    proposal = Proposal(
        supplier_id=supplier.id,
        procurement_event_id=procurement_event.id,
    )

    db.add(proposal)
    db.commit()

    document = Document(
        proposal_id=proposal.id,
    )

    db.add(document)
    db.commit()

    document_version = DocumentVersion(
        document_id=document.id,
        filename="dell-pricing.pdf",
        content_type="application/pdf",
        sha256="a" * 64,
        storage_key = "test/dell-pricing.pdf"
    )

    db.add(document_version)
    db.commit()

    assert document.proposal.id == proposal.id
    assert proposal.documents[0].id == document.id

    assert document_version.document.id == document.id
    assert document.versions[0].id == document_version.id
