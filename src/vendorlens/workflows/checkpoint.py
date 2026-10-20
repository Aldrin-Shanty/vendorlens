from collections.abc import Generator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy.engine import make_url


@contextmanager
def open_checkpointer(
    database_url: str,
) -> Generator[PostgresSaver, None, None]:
    """Open a PostgreSQL checkpointer for the lifetime of this context."""
    url = make_url(database_url)

    if url.get_backend_name() != "postgresql":
        raise ValueError(
            "Workflow checkpoints require PostgreSQL"
        )

    connection_string = url.set(
        drivername="postgresql"
    ).render_as_string(hide_password=False)

    with PostgresSaver.from_conn_string(
        connection_string
    ) as checkpointer:
        yield checkpointer


def initialize_checkpoints(database_url: str) -> None:
    """Create or upgrade LangGraph's checkpoint tables."""
    with open_checkpointer(database_url) as checkpointer:
        checkpointer.setup()
