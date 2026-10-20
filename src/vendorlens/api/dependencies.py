from collections.abc import Generator

from sqlalchemy.orm import Session

from langgraph.checkpoint.postgres import PostgresSaver

from vendorlens.db.models.session import SessionLocal
from vendorlens.db.engine import engine
from vendorlens.workflows.checkpoint import open_checkpointer

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()

def get_checkpointer() -> Generator[PostgresSaver, None, None]:
    database_url = engine.url.render_as_string(
        hide_password=False,
    )

    with open_checkpointer(database_url) as checkpointer:
        yield checkpointer
