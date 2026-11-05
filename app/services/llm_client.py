"""OpenAI Chat Completions adapter with strict parsing and safe error mapping."""

import json

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import GeneratedCopy, ProductInput
from app.services.prompt_builder import SYSTEM_PROMPT, build_repair_prompt, build_user_prompt


class LLMError(RuntimeError):
    """Base class for provider failures safe to handle at the API boundary."""


class LLMConfigurationError(LLMError):
    """Required OpenAI API configuration is missing."""


class LLMUnavailableError(LLMError):
    """The provider or configured model is unavailable."""


class LLMTimeoutError(LLMError):
    """The provider did not respond within the configured timeout."""


class LLMProviderError(LLMError):
    """The provider returned an unsuccessful HTTP response."""


class LLMResponseError(LLMError):
    """The provider returned an invalid or incomplete response."""

    def __init__(self, message: str, *, candidate: str | None = None) -> None:
        super().__init__(message)
        self.candidate = candidate


class LLMRefusalError(LLMError):
    """The model refused to generate the requested content."""


class LLMClient:
    """Generate only textual copy using OpenAI strict JSON Schema output."""

    def __init__(
        self,
        config: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport

    async def generate_copy(
        self,
        product: ProductInput,
        *,
        previous_response: str | None = None,
        repair_errors: list[str] | None = None,
    ) -> GeneratedCopy:
        """Generate or repair validated textual fields without source characteristics."""
        api_key = self.config.openai_api_key
        if api_key is None or not api_key.strip():
            raise LLMConfigurationError("Не задан ключ OpenAI API")
        model = self.config.openai_model
        if not model.strip():
            raise LLMConfigurationError("Не задана модель OpenAI")

        try:
            provider_url = httpx.URL(
                f"{self.config.openai_base_url.rstrip('/')}/chat/completions"
            )
            if provider_url.scheme not in {"http", "https"} or provider_url.host is None:
                raise ValueError("unsupported API URL")
        except (httpx.InvalidURL, ValueError) as exc:
            raise LLMConfigurationError("Некорректно настроен адрес OpenAI API") from exc
        url = str(provider_url)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(product)},
        ]
        if repair_errors is not None:
            messages.append(
                {
                    "role": "user",
                    "content": build_repair_prompt(previous_response, repair_errors),
                }
            )

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "product_card_copy",
                    "strict": True,
                    "schema": GeneratedCopy.model_json_schema(),
                },
            },
        }

        candidate: str | None = None
        try:
            async with httpx.AsyncClient(
                timeout=self.config.llm_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key.strip()}"},
                )
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Истекло время ожидания ответа OpenAI API") from exc
        except httpx.InvalidURL as exc:
            raise LLMConfigurationError("Некорректно настроен адрес OpenAI API") from exc
        except httpx.RequestError as exc:
            raise LLMUnavailableError("Сервис OpenAI API недоступен") from exc

        if response.status_code in (401, 403):
            raise LLMConfigurationError("Ключ или разрешения OpenAI API не приняты")
        if response.status_code == 404:
            raise LLMUnavailableError("Указанная модель OpenAI недоступна")
        if response.status_code == 429 or response.status_code >= 500:
            raise LLMUnavailableError("Сервис OpenAI API временно недоступен")
        if response.is_error:
            raise LLMProviderError(f"OpenAI API вернул HTTP {response.status_code}")

        try:
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError("invalid response shape")
            choices = body["choices"]
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise TypeError("invalid choices shape")
            message = choices[0]["message"]
            if not isinstance(message, dict):
                raise TypeError("invalid message shape")
            if message.get("refusal"):
                raise LLMRefusalError("Модель отказалась подготовить черновик")
            content = message["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty model content")
            candidate = content
            generated_data = json.loads(content)
            return GeneratedCopy.model_validate(generated_data)
        except LLMRefusalError:
            raise
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise LLMResponseError(
                "OpenAI API вернул некорректный ответ", candidate=candidate
            ) from exc
