import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from vendorlens.db.base import Base


class ComparisonWorkflowCounter(Base):
    __tablename__ = "comparison_workflow_counters"

    procurement_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procurement_events.id", ondelete="CASCADE"), primary_key=True
    )
    supplier_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False)


class ComparisonWorkflowRecord(Base):
    __tablename__ = "comparison_workflow_records"
    __table_args__ = (
        UniqueConstraint("procurement_event_id", "supplier_key", "sequence_number", name="uq_workflow_group_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    procurement_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("procurement_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supplier_key: Mapped[str] = mapped_column(String(64), nullable=False)
    supplier_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
