import os
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from vendorlens.api.dependencies import get_db
from vendorlens.api.main import app
from vendorlens.db.base import Base
from vendorlens.db.models.supplier import Supplier

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if TEST_DATABASE_URL is None:
    raise RuntimeError("TEST_DATABASE_URL environment variable is not set")

test_engine = create_engine(TEST_DATABASE_URL)

@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    yield

    Base.metadata.drop_all(bind=test_engine)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    expire_on_commit=False,
)

def override_get_db():
    db = TestSessionLocal()

    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
