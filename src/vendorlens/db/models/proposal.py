from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vendorlens.db.base import Base

if TYPE_CHECKING:
    from vendorlens.db.models.procurement_event import ProcurementEvent
    from vendorlens.db.models.supplier import Supplier
    from vendorlens.db.models.document import Document

class Proposal(Base):
    __tablename__ = "proposals"

    __table_args__ = (
        UniqueConstraint(
            "supplier_id",
            "procurement_event_id",
            name="uq_proposal_supplier_event",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suppliers.id"),
        nullable=False,
    )

    procurement_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("procurement_events.id"),
        nullable=False,
    )

    supplier: Mapped[Supplier] = relationship(
        back_populates="proposals",
    )

    procurement_event: Mapped[ProcurementEvent] = relationship(
        back_populates="proposals",
    )

    documents: Mapped[list[Document]] = relationship(
    back_populates="proposal",
    )
