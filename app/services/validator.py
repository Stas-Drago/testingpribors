"""Validate model output and build source-backed technical characteristics."""

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.schemas import Characteristic, GeneratedCopy, ProductInput

_NUMBER_PATTERN = re.compile(r"(?<!\d)\d+(?:[.,]\d+)?")


@dataclass
class ValidationResult:
    """Separate blocking output violations from manual-review warnings."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _normalized_numbers(text: str) -> list[tuple[str, Decimal]]:
    numbers: list[tuple[str, Decimal]] = []
    for token in _NUMBER_PATTERN.findall(text):
        try:
            number = Decimal(token.replace(",", "."))
        except InvalidOperation:
            continue
        numbers.append((token, number))
    return numbers


def build_characteristics(product: ProductInput) -> list[Characteristic]:
    """Copy characteristics from input; never ask the LLM to author technical values."""
    return [
        Characteristic(name=name, value=value if value.strip() else "данных нет")
        for name, value in product.specs.items()
    ]


def find_missing_data(product: ProductInput) -> list[str]:
    """Report missing input sections only; do not assume universal instrument fields."""
    missing: list[str] = []
    if not product.manufacturer:
        missing.append("Производитель: данных нет")
    if not product.description:
        missing.append("Описание: данных нет")
    if not product.specs:
        missing.append("Технические характеристики: данных нет")
    else:
        missing.extend(
            f"{name}: данных нет" for name, value in product.specs.items() if not value.strip()
        )
    return missing


def validate_generated_copy(
    copy: GeneratedCopy | dict[str, object], product: ProductInput
) -> ValidationResult:
    """Validate generated fields and flag numbers not present in source data.

    Numeric warnings are advisory only: they never make the copy invalid and never
    request another model response.
    """
    try:
        generated = GeneratedCopy.model_validate(copy)
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_context=False, include_url=False)
        ]
        return ValidationResult(errors=errors)

    errors: list[str] = []
    text_fields = {
        "seo_title": generated.seo_title,
        "seo_description": generated.seo_description,
        "commercial_block": generated.commercial_block,
    }
    for field_name, value in text_fields.items():
        if not value.strip():
            errors.append(f"{field_name}: поле не должно быть пустым")

    title_length = len(generated.seo_title)
    if title_length > 70:
        errors.append(f"seo_title: длина {title_length}, допустимо не более 70 символов")

    description_length = len(generated.seo_description)
    if not 800 <= description_length <= 1200:
        errors.append(
            f"seo_description: длина {description_length}, допустимо от 800 до 1 200 символов"
        )

    if not 3 <= len(generated.search_queries) <= 5:
        errors.append(
            "search_queries: требуется от 3 до 5 поисковых запросов "
            f"(получено {len(generated.search_queries)})"
        )
    for index, query in enumerate(generated.search_queries, start=1):
        if not query.strip():
            errors.append(f"search_queries[{index - 1}]: запрос не должен быть пустым")

    source_numbers = {
        number
        for source_text in _strings(product.model_dump(mode="python"))
        for _, number in _normalized_numbers(source_text)
    }
    generated_text = "\n".join(
        [generated.seo_title, generated.seo_description, *generated.search_queries, generated.commercial_block]
    )
    warnings: list[str] = []
    seen_unmatched: set[Decimal] = set()
    for token, number in _normalized_numbers(generated_text):
        if number not in source_numbers and number not in seen_unmatched:
            seen_unmatched.add(number)
            warnings.append(
                f"В тексте есть число «{token}», которого нет во входных данных; "
                "проверьте вручную."
            )

    return ValidationResult(errors=errors, warnings=warnings)
