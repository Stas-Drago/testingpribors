"""API and workspace integration tests; the LLM is always replaced by a stub."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.main import app, get_draft_service
from app.schemas import ProductDraft
from app.services.draft_service import DraftValidationError
from app.services.llm_client import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRefusalError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)

client = TestClient(app)
PRODUCT = {
    "name": "Манометр показывающий DM 02",
    "manufacturer": "Манотомь",
    "specs": {"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5"},
    "description": "Прибор предназначен для измерения избыточного давления.",
}
DRAFT = ProductDraft(
    seo_title="Манометр DM 02 — Манотомь",
    seo_description="Описание прибора для измерения давления.",
    characteristics=[
        {"name": "Диапазон измерений", "value": "0–1,6 МПа"},
        {"name": "Класс точности", "value": "1,5"},
    ],
    search_queries=["манометр DM 02", "манометр Манотомь", "манометр давления"],
    commercial_block="Подходит для измерения избыточного давления.",
    missing_data=[],
    warnings=[],
)


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_health_is_available_without_local_model(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert client.get("/health").json() == {"status": "ok"}


def test_get_workspace_contains_editor_tabs_and_copy_actions() -> None:
    response = client.get("/")
    assert response.status_code == 200
    for marker in ("Исходные данные", "Предпросмотр", "Markdown", "JSON", "Копировать Markdown", "Копировать JSON"):
        assert marker in response.text
    assert "cdn." not in response.text


def test_invalid_json_returns_safe_422_without_echoing_input() -> None:
    payload = '{"name": "sensitive product payload",'
    response = client.post("/api/products/draft", content=payload, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "sensitive product payload" not in response.text


def test_invalid_product_schema_returns_422() -> None:
    response = client.post("/api/products/draft", json={"name": "   "})
    assert response.status_code == 422


def test_successful_generation_returns_explicit_draft_response() -> None:
    service = AsyncMock()
    service.create_draft.return_value = DRAFT
    app.dependency_overrides[get_draft_service] = lambda: service
    response = client.post("/api/products/draft", json=PRODUCT)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"draft", "markdown"}
    assert body["draft"]["seo_title"] == DRAFT.seo_title
    assert body["draft"]["characteristics"][0]["value"] == "0–1,6 МПа"
    assert "## SEO-заголовок" in body["markdown"]
    service.create_draft.assert_awaited_once()


@pytest.mark.parametrize("error", [LLMConfigurationError("hidden"), LLMUnavailableError("hidden")])
def test_configuration_and_unavailable_model_map_to_503(error) -> None:
    service = AsyncMock()
    service.create_draft.side_effect = error
    app.dependency_overrides[get_draft_service] = lambda: service
    response = client.post("/api/products/draft", json=PRODUCT)
    assert response.status_code == 503
    assert "hidden" not in response.text


@pytest.mark.parametrize("error", [
    LLMProviderError("private"), LLMResponseError("private"), LLMRefusalError("private"),
    DraftValidationError(["private"]),
])
def test_provider_and_invalid_results_map_to_safe_502(error) -> None:
    service = AsyncMock()
    service.create_draft.side_effect = error
    app.dependency_overrides[get_draft_service] = lambda: service
    response = client.post("/api/products/draft", json=PRODUCT)
    assert response.status_code == 502
    assert "private" not in response.text


def test_timeout_maps_to_504() -> None:
    service = AsyncMock()
    service.create_draft.side_effect = LLMTimeoutError("private")
    app.dependency_overrides[get_draft_service] = lambda: service
    response = client.post("/api/products/draft", json=PRODUCT)
    assert response.status_code == 504
    assert "private" not in response.text
