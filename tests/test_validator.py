"""Tests proving source facts and missing-data reports are deterministic."""

import pytest

from app.schemas import GeneratedCopy, ProductInput
from app.services.validator import (
    build_characteristics,
    find_missing_data,
    validate_generated_copy,
)


def _copy(
    *, title: str = "Манометр DM 02", description: str = "О" * 800,
    queries: list[str] | None = None, commercial: str = "Для измерения давления.",
) -> GeneratedCopy:
    return GeneratedCopy(
        seo_title=title,
        seo_description=description,
        search_queries=queries or ["манометр DM 02", "Манотомь DM 02", "прибор для давления"],
        commercial_block=commercial,
    )


def test_characteristics_are_copied_one_to_one_from_source() -> None:
    product = ProductInput(
        name="Манометр DM 02",
        specs={" диапазон ": " 0–1,6 МПа ", "Класс точности": "1,5"},
    )

    characteristics = build_characteristics(product)

    assert [(item.name, item.value, item.source) for item in characteristics] == [
        (" диапазон ", " 0–1,6 МПа ", "specs"),
        ("Класс точности", "1,5", "specs"),
    ]


def test_blank_spec_value_is_marked_missing_without_losing_its_name() -> None:
    product = ProductInput(name="Манометр DM 02", specs={"Присоединение": "   "})

    assert [(item.name, item.value) for item in build_characteristics(product)] == [
        ("Присоединение", "данных нет")
    ]
    assert "Присоединение: данных нет" in find_missing_data(product)


def test_missing_data_reports_only_empty_input_sections() -> None:
    product = ProductInput(name="Прибор")

    assert find_missing_data(product) == [
        "Производитель: данных нет",
        "Описание: данных нет",
        "Технические характеристики: данных нет",
    ]


def test_missing_data_does_not_invent_unprovided_characteristic_names() -> None:
    product = ProductInput(name="Прибор", specs={"Диапазон": "0–10 бар"})

    missing = find_missing_data(product)

    assert "Диапазон: данных нет" not in missing
    assert all("питание" not in item.lower() for item in missing)
    assert all("интерфейс" not in item.lower() for item in missing)


def test_blank_characteristic_name_is_rejected_at_input_boundary() -> None:
    with pytest.raises(ValueError, match="Название характеристики"):
        ProductInput(name="Прибор", specs={"   ": "значение"})


@pytest.mark.parametrize(("length", "valid"), [(69, True), (70, True), (71, False)])
def test_title_length_boundaries(length: int, valid: bool) -> None:
    result = validate_generated_copy(_copy(title="Т" * length), ProductInput(name="Прибор"))

    assert (not any(error.startswith("seo_title:") for error in result.errors)) is valid


@pytest.mark.parametrize(
    ("length", "valid"), [(799, False), (800, True), (1200, True), (1201, False)]
)
def test_description_length_boundaries(length: int, valid: bool) -> None:
    result = validate_generated_copy(
        _copy(description="О" * length), ProductInput(name="Прибор")
    )

    assert (not any(error.startswith("seo_description:") for error in result.errors)) is valid


@pytest.mark.parametrize(("count", "valid"), [(2, False), (3, True), (5, True), (6, False)])
def test_search_query_count_boundaries(count: int, valid: bool) -> None:
    queries = [f"запрос {index}" for index in range(count)]
    result = validate_generated_copy(_copy(queries=queries), ProductInput(name="Прибор"))

    assert (not any(error.startswith("search_queries:") for error in result.errors)) is valid


@pytest.mark.parametrize(
    "payload",
    [
        {"seo_title": "", "seo_description": "О" * 800},
        {"seo_title": "Прибор", "seo_description": "О" * 800, "search_queries": ["x", 4]},
    ],
)
def test_empty_or_wrong_type_generated_fields_are_errors(payload: dict[str, object]) -> None:
    result = validate_generated_copy(payload, ProductInput(name="Прибор"))

    assert result.errors


def test_numeric_comparison_normalizes_decimal_comma_and_point() -> None:
    product = ProductInput(name="Манометр DM 02", description="Диапазон 0–1,6 МПа")
    generated = _copy(description=("Диапазон от 0 до 1.6 МПа. " + "О" * 780)[:800])

    result = validate_generated_copy(generated, product)

    assert not result.errors
    assert not result.warnings


def test_unsupported_number_is_warning_not_validation_error() -> None:
    result = validate_generated_copy(
        _copy(title="Манометр на 100 бар"), ProductInput(name="Манометр")
    )

    assert not result.errors
    assert any("100" in warning for warning in result.warnings)


def test_empty_specs_are_valid_and_do_not_invent_characteristics() -> None:
    product = ProductInput(name="Прибор")

    assert build_characteristics(product) == []
    assert "Технические характеристики: данных нет" in find_missing_data(product)
