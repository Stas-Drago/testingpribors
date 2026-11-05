"""Tests proving source facts and missing-data reports are deterministic."""

import pytest

from app.schemas import ProductInput
from app.services.validator import build_characteristics, find_missing_data


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
