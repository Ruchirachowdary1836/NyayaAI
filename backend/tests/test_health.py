import time

from backend.app.core.config import Settings
from backend.app.main import app
from fastapi.testclient import TestClient


def test_default_retriever_configuration_is_safe() -> None:
    assert Settings(_env_file=None).enabled_retrievers == ["bm25"]


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_ready_endpoint() -> None:
    with TestClient(app) as client:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            response = client.get("/ready")
            if response.status_code == 200:
                break
            assert response.status_code == 503
            time.sleep(0.01)
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
