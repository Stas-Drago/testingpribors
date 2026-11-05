"""Orchestrate generation, one constrained repair attempt, and draft assembly."""

from typing import Protocol

from app.config import settings
from app.schemas import GeneratedCopy, ProductDraft, ProductInput
from app.services.llm_client import LLMClient, LLMResponseError
from app.services.validator import (
    ValidationResult,
    build_characteristics,
    find_missing_data,
    validate_generated_copy,
)


class CopyGenerator(Protocol):
    async def generate_copy(
        self,
        product: ProductInput,
        *,
        previous_response: str | None = None,
        repair_errors: list[str] | None = None,
    ) -> GeneratedCopy: ...


class DraftValidationError(RuntimeError):
    """Generation remained invalid after its single repair attempt."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Модель не смогла подготовить корректный текст черновика")


class DraftService:
    """Generate a draft while keeping source-backed facts under application control."""

    def __init__(self, llm_client: CopyGenerator | None = None) -> None:
        self.llm_client = llm_client or LLMClient(settings)

    @staticmethod
    def _build_draft(product: ProductInput, generated: GeneratedCopy, result: ValidationResult):
        return ProductDraft(
            **generated.model_dump(),
            characteristics=build_characteristics(product),
            missing_data=find_missing_data(product),
            warnings=result.warnings,
        )

    async def create_draft(self, product: ProductInput) -> ProductDraft:
        """Generate, validate, and if needed repair copy exactly once."""
        previous_response: str | None = None
        validation_errors: list[str]

        try:
            generated = await self.llm_client.generate_copy(product)
            first_result = validate_generated_copy(generated, product)
            if first_result.is_valid:
                return self._build_draft(product, generated, first_result)
            previous_response = generated.model_dump_json()
            validation_errors = first_result.errors
        except LLMResponseError as exc:
            previous_response = exc.candidate
            validation_errors = ["Формат ответа модели некорректен; верните валидный JSON по схеме."]

        try:
            repaired = await self.llm_client.generate_copy(
                product,
                previous_response=previous_response,
                repair_errors=validation_errors,
            )
        except LLMResponseError as exc:
            raise DraftValidationError(
                ["Формат ответа модели остался некорректным после исправления."]
            ) from exc

        repair_result = validate_generated_copy(repaired, product)
        if not repair_result.is_valid:
            raise DraftValidationError(repair_result.errors)
        return self._build_draft(product, repaired, repair_result)
