"""Tests for draft validation and the single-repair policy."""

from collections import deque

import anyio
import pytest

from app.schemas import GeneratedCopy, ProductInput
from app.services.draft_service import DraftService, DraftValidationError
from app.services.llm_client import LLMProviderError, LLMResponseError


def _product() -> ProductInput:
    return ProductInput(
        name="Манометр DM 02",
        manufacturer="Манотомь",
        specs={"Диапазон": "0–1,6 МПа"},
        description="Для измерения давления в диапазоне 0–1,6 МПа.",
    )


def _copy(*, title: str = "Манометр DM 02", description: str = "О" * 800) -> GeneratedCopy:
    return GeneratedCopy(
        seo_title=title,
        seo_description=description,
        search_queries=["манометр DM 02", "Манотомь DM 02", "манометр давления"],
        commercial_block="Для измерения давления.",
    )


class FakeGenerator:
    def __init__(self, responses: list[GeneratedCopy | Exception]) -> None:
        self.responses = deque(responses)
        self.calls: list[dict[str, object]] = []

    async def generate_copy(
        self,
        product: ProductInput,
        *,
        previous_response: str | None = None,
        repair_errors: list[str] | None = None,
    ) -> GeneratedCopy:
        self.calls.append(
            {"product": product, "previous_response": previous_response, "repair_errors": repair_errors}
        )
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def test_valid_response_is_assembled_without_retry() -> None:
    generator = FakeGenerator([_copy()])

    draft = anyio.run(DraftService(generator).create_draft, _product())

    assert len(generator.calls) == 1
    assert [(item.name, item.value) for item in draft.characteristics] == [
        ("Диапазон", "0–1,6 МПа")
    ]
    assert draft.warnings == []


def test_invalid_length_is_repaired_once_and_revalidated() -> None:
    generator = FakeGenerator([_copy(title="Т" * 71), _copy()])

    draft = anyio.run(DraftService(generator).create_draft, _product())

    assert len(generator.calls) == 2
    assert generator.calls[1]["previous_response"]
    assert any("seo_title" in error for error in generator.calls[1]["repair_errors"])
    assert draft.seo_title == "Манометр DM 02"


def test_second_invalid_result_raises_controlled_error_without_third_call() -> None:
    generator = FakeGenerator([_copy(title="Т" * 71), _copy(title="Д" * 71)])

    with pytest.raises(DraftValidationError, match="не смогла подготовить корректный"):
        anyio.run(DraftService(generator).create_draft, _product())

    assert len(generator.calls) == 2


def test_malformed_response_gets_one_repair_attempt() -> None:
    generator = FakeGenerator([LLMResponseError("malformed", candidate="not json"), _copy()])

    draft = anyio.run(DraftService(generator).create_draft, _product())

    assert len(generator.calls) == 2
    assert generator.calls[1]["previous_response"] == "not json"
    assert draft.seo_title == "Манометр DM 02"


def test_provider_failure_is_not_retried() -> None:
    generator = FakeGenerator([LLMProviderError("provider failure")])

    with pytest.raises(LLMProviderError):
        anyio.run(DraftService(generator).create_draft, _product())

    assert len(generator.calls) == 1


def test_unknown_numeric_token_warns_without_retry() -> None:
    generator = FakeGenerator([_copy(title="Манометр 42")])

    draft = anyio.run(DraftService(generator).create_draft, _product())

    assert len(generator.calls) == 1
    assert any("42" in warning for warning in draft.warnings)
