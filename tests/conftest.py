import os
import pytest
from fastapi.testclient import TestClient

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from vendorlens.api.storage_dependencies import get_storage
from vendorlens.services.storage import LocalFileStorage
from vendorlens.api.dependencies import get_db
from vendorlens.api.main import app
from vendorlens.db.base import Base
from vendorlens.core.security import API_KEY

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if TEST_DATABASE_URL is None:
    raise RuntimeError("TEST_DATABASE_URL environment variable is not set")

test_engine = create_engine(TEST_DATABASE_URL)

with test_engine.begin() as connection:
    connection.execute(
        text("CREATE EXTENSION IF NOT EXISTS vector")
    )

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    expire_on_commit=False,
)

@pytest.fixture(autouse=True)
def disable_model_judgment(monkeypatch):
    # Unit tests must not load models based on a developer's environment.
    monkeypatch.setenv("NLI_EVIDENCE_JUDGMENT_ENABLED", "false")


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    yield

    Base.metadata.drop_all(bind=test_engine)

@pytest.fixture
def client():
    if API_KEY is None:
        raise RuntimeError("API_KEY environment variable is not set")
    with TestClient(app, headers={"X-API-Key": API_KEY}) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = TestSessionLocal()

    try:
        yield session
    finally:
        session.close()

@pytest.fixture
def temp_storage(tmp_path):
    storage = LocalFileStorage(tmp_path)

    app.dependency_overrides[get_storage] = lambda: storage

    try:
        yield storage
    finally:
        app.dependency_overrides.pop(get_storage, None)

def override_get_db():
    db = TestSessionLocal()

    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
