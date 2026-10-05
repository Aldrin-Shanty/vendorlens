import uuid

from fastapi.testclient import TestClient

from vendorlens.api.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    request_id = response.headers["X-Request-ID"]

    uuid.UUID(request_id)
