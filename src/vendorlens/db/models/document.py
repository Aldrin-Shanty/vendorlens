from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vendorlens.db.base import Base


if TYPE_CHECKING:
    from vendorlens.db.models.document_version import DocumentVersion
    from vendorlens.db.models.proposal import Proposal


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("proposals.id"),
        nullable=False,
    )

    proposal: Mapped[Proposal] = relationship(
        back_populates="documents",
    )

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
    )
