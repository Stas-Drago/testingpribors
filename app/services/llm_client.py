"""Ollama API adapter with strict parsing and safe error mapping."""

import json

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import GeneratedCopy, ProductInput
from app.services.prompt_builder import SYSTEM_PROMPT, build_repair_prompt, build_user_prompt


class LLMError(RuntimeError):
    """Base class for provider failures safe to handle at the API boundary."""


class LLMConfigurationError(LLMError):
    """Required local model configuration is missing."""


class LLMUnavailableError(LLMError):
    """Ollama server or configured model is unavailable."""


class LLMTimeoutError(LLMError):
    """Ollama did not respond within the configured timeout."""


class LLMProviderError(LLMError):
    """Ollama returned an unsuccessful HTTP response."""


class LLMResponseError(LLMError):
    """Ollama returned an invalid or incomplete response."""

    def __init__(self, message: str, *, candidate: str | None = None) -> None:
        super().__init__(message)
        self.candidate = candidate


class LLMRefusalError(LLMError):
    """The model refused to generate the requested content."""


class LLMClient:
    """Generate only textual copy using Ollama's local structured-output endpoint."""

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
        model = self.config.ollama_model
        if model is None or not model.strip():
            raise LLMConfigurationError("Не задана локальная модель Ollama")

        url = f"{self.config.ollama_base_url.rstrip('/')}/api/chat"
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
            "think": False,
            "format": GeneratedCopy.model_json_schema(),
        }

        candidate: str | None = None
        try:
            async with httpx.AsyncClient(
                timeout=self.config.llm_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Истекло время ожидания ответа локальной модели") from exc
        except httpx.RequestError as exc:
            raise LLMUnavailableError("Локальный сервер Ollama недоступен") from exc

        if response.status_code == 404:
            raise LLMUnavailableError("Локальная модель Ollama не найдена")
        if response.is_error:
            raise LLMProviderError(f"Локальный сервер Ollama вернул HTTP {response.status_code}")

        try:
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError("invalid response shape")
            message = body["message"]
            if not isinstance(message, dict):
                raise TypeError("invalid message shape")
            if message.get("refusal"):
                raise LLMRefusalError("Модель отказалась подготовить черновик")
            content = message["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty model content")
            generated_data = json.loads(content)
            return GeneratedCopy.model_validate(generated_data)
        except LLMRefusalError:
            raise
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            raise LLMResponseError(
                "Локальная модель вернула некорректный ответ", candidate=candidate
            ) from exc
