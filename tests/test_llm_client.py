"""Mocked HTTP contract and failure tests for the local Ollama client."""

import json

import httpx
import pytest

from app.config import Settings
from app.schemas import GeneratedCopy, ProductInput
from app.services.llm_client import (
    LLMClient,
    LLMConfigurationError,
    LLMProviderError,
    LLMRefusalError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)


def _config(**overrides: object) -> Settings:
    return Settings(_env_file=None, ollama_model="qwen3:8b", **overrides)


def _product() -> ProductInput:
    return ProductInput(
        name="Манометр DM 02",
        manufacturer="Манотомь",
        specs={"диапазон измерений": "0–1,6 МПа"},
        description="Измерение избыточного давления.",
    )


def _generated_data() -> dict[str, object]:
    return {
        "seo_title": "Манометр показывающий DM 02",
        "seo_description": "Описание прибора на основании переданных данных.",
        "search_queries": ["манометр DM 02", "Манотомь DM 02", "манометр 0–1,6 МПа"],
        "commercial_block": "Для измерения избыточного давления.",
    }


def test_client_sends_ollama_chat_contract_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(_generated_data())}},
        )

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))

    import anyio

    result = anyio.run(client.generate_copy, _product())

    payload = captured["payload"]
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert isinstance(payload, dict)
    assert payload["model"] == "qwen3:8b"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert "format" in payload
    assert payload["format"]["additionalProperties"] is False
    assert set(payload["format"]["properties"]) == {
        "seo_title",
        "seo_description",
        "search_queries",
        "commercial_block",
    }
    assert set(payload["format"]["required"]) == {
        "seo_title",
        "seo_description",
        "search_queries",
        "commercial_block",
    }
    assert result == GeneratedCopy.model_validate(_generated_data())


def test_client_accepts_repair_context_without_changing_source_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": json.dumps(_generated_data())}},
        )

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))

    import anyio

    async def generate_repair() -> GeneratedCopy:
        return await client.generate_copy(
            _product(),
            previous_response='{"seo_title":"слишком длинный"}',
            repair_errors=["seo_title: длина превышает лимит"],
        )

    anyio.run(generate_repair)

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert len(payload["messages"]) == 3
    assert "product_json" in payload["messages"][1]["content"]
    repair_message = payload["messages"][2]["content"]
    assert "только исходные четыре текстовых поля" in repair_message
    assert "seo_title: длина превышает лимит" in repair_message
    assert '"previous_response"' in repair_message


def test_missing_model_fails_before_http_request() -> None:
    client = LLMClient(Settings(_env_file=None))

    import anyio

    with pytest.raises(LLMConfigurationError, match="Не задана локальная модель"):
        anyio.run(client.generate_copy, _product())


def test_unavailable_ollama_is_mapped_safely() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private details", request=request)

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))

    import anyio

    with pytest.raises(LLMUnavailableError, match="недоступен") as exc_info:
        anyio.run(client.generate_copy, _product())
    assert "private details" not in str(exc_info.value)


def test_timeout_is_mapped_safely() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private details", request=request)

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))

    import anyio

    with pytest.raises(LLMTimeoutError, match="время ожидания"):
        anyio.run(client.generate_copy, _product())


@pytest.mark.parametrize("status_code", [400, 404, 429, 500, 503])
def test_http_errors_are_mapped_without_response_body(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="sensitive provider detail")

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))
    import anyio

    expected_error = LLMUnavailableError if status_code == 404 else LLMProviderError
    with pytest.raises(expected_error) as exc_info:
        anyio.run(client.generate_copy, _product())
    assert "sensitive provider detail" not in str(exc_info.value)


def test_model_refusal_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "{}", "refusal": True}},
        )

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))
    import anyio

    with pytest.raises(LLMRefusalError):
        anyio.run(client.generate_copy, _product())


@pytest.mark.parametrize(
    "body",
    [
        {"message": {"role": "assistant", "content": "not json"}},
        {"message": {"role": "assistant", "content": "{}"}},
        {"message": {"role": "assistant", "content": ""}},
        {"message": {"role": "assistant"}},
        {"unexpected": True},
    ],
)
def test_malformed_or_incomplete_response_is_mapped(body: dict[str, object]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))
    import anyio

    with pytest.raises(LLMResponseError):
        anyio.run(client.generate_copy, _product())
