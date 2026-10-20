"""Keep evidence deletion from racing a comparison that is using it."""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_records(db: Session, keys: list[str], *, shared: bool) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    for key in sorted(set(keys)):
        db.execute(text(f"SELECT {function}(hashtextextended(:key, 0))"), {"key": key})


def lock_comparison_data(db: Session, event_id: uuid.UUID, supplier_ids: list[uuid.UUID]) -> None:
    lock_records(db, [f"event:{event_id}", *(f"supplier:{supplier_id}" for supplier_id in supplier_ids)], shared=True)
