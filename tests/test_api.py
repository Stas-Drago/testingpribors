"""API validation and health checks that do not call the LLM provider."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_available_without_local_model(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_invalid_json_returns_422() -> None:
    response = client.post(
        "/api/products/draft",
        content='{"name": "Манометр",',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_invalid_product_schema_returns_422() -> None:
    response = client.post("/api/products/draft", json={"name": "   "})

    assert response.status_code == 422
