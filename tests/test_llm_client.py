"""Mocked HTTP contract and failure tests for the OpenAI API client."""

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
    return Settings(
        _env_file=None,
        openai_api_key="test-secret",
        openai_model="gpt-4o-mini",
        **overrides,
    )


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


def _response(data: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": json.dumps(data)}}]},
    )


def test_client_sends_openai_chat_contract_and_parses_response() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return _response(_generated_data())

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))

    import anyio

    result = anyio.run(client.generate_copy, _product())

    payload = captured["payload"]
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer test-secret"
    assert isinstance(payload, dict)
    assert payload["model"] == "gpt-4o-mini"
    assert payload["stream"] is False
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    schema = payload["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["properties"]) == {
        "seo_title",
        "seo_description",
        "search_queries",
        "commercial_block",
    }
    assert set(schema["schema"]["required"]) == set(schema["schema"]["properties"])
    assert result == GeneratedCopy.model_validate(_generated_data())


def test_client_accepts_repair_context_without_changing_source_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _response(_generated_data())

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


def test_missing_api_key_fails_before_http_request() -> None:
    client = LLMClient(Settings(_env_file=None))

    import anyio

    with pytest.raises(LLMConfigurationError, match="Не задан ключ OpenAI API"):
        anyio.run(client.generate_copy, _product())


def test_custom_base_url_is_supported() -> None:
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(str(request.url))
        return _response(_generated_data())

    client = LLMClient(
        _config(openai_base_url="https://gateway.example/v1/"),
        transport=httpx.MockTransport(handler),
    )
    import anyio

    anyio.run(client.generate_copy, _product())
    assert captured == ["https://gateway.example/v1/chat/completions"]


def test_invalid_base_url_is_mapped_to_safe_configuration_error() -> None:
    client = LLMClient(_config(openai_base_url="not a url"))
    import anyio

    with pytest.raises(LLMConfigurationError, match="адрес OpenAI API"):
        anyio.run(client.generate_copy, _product())


def test_unavailable_provider_is_mapped_safely() -> None:
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


@pytest.mark.parametrize("status_code", [400])
def test_http_errors_are_mapped_without_response_body(status_code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="sensitive provider detail")

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))
    import anyio

    with pytest.raises(LLMProviderError) as exc_info:
        anyio.run(client.generate_copy, _product())
    assert "sensitive provider detail" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, LLMConfigurationError),
        (403, LLMConfigurationError),
        (429, LLMUnavailableError),
        (500, LLMUnavailableError),
        (503, LLMUnavailableError),
    ],
)
def test_auth_and_temporary_http_errors_are_mapped_safely(status_code, error_type) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text="sensitive provider detail")

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))
    import anyio

    with pytest.raises(error_type) as exc_info:
        anyio.run(client.generate_copy, _product())
    assert "sensitive provider detail" not in str(exc_info.value)


def test_unknown_model_is_mapped_as_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="sensitive model detail")

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))
    import anyio

    with pytest.raises(LLMUnavailableError):
        anyio.run(client.generate_copy, _product())


def test_model_refusal_is_mapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": None, "refusal": "not allowed"}}]},
        )

    client = LLMClient(_config(), transport=httpx.MockTransport(handler))
    import anyio

    with pytest.raises(LLMRefusalError):
        anyio.run(client.generate_copy, _product())


@pytest.mark.parametrize(
    "body",
    [
        {"choices": [{"message": {"role": "assistant", "content": "not json"}}]},
        {"choices": [{"message": {"role": "assistant", "content": "{}"}}]},
        {"choices": [{"message": {"role": "assistant", "content": ""}}]},
        {"choices": [{"message": {"role": "assistant"}}]},
        {"choices": []},
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
