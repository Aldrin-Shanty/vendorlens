from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vendorlens.db.base import Base

if TYPE_CHECKING:
    from vendorlens.db.models.proposal import Proposal


class ProcurementEvent(Base):
    __tablename__ = "procurement_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    proposals: Mapped[list[Proposal]] = relationship(
        back_populates="procurement_event",
    )
