"""Validate documented product examples and their provenance."""

import json
import re
from pathlib import Path

from app.schemas import ProductInput

ROOT = Path(__file__).parents[1]


def _product(filename: str) -> ProductInput:
    data = json.loads((ROOT / "examples" / filename).read_text(encoding="utf-8"))
    return ProductInput.model_validate(data)


def test_both_example_products_match_input_schema() -> None:
    first = _product("product_1.json")
    second = _product("product_2.json")
    assert first.name == "Манометр показывающий DM 02"
    assert first.specs["диапазон измерений"] == "0–1,6 МПа"
    assert second.name.startswith("Fluke 117")
    assert second.manufacturer == "Fluke"
    assert len(second.specs) >= 5


def test_fluke_source_documents_all_selected_fields() -> None:
    source = (ROOT / "examples" / "SOURCES.md").read_text(encoding="utf-8")
    product = _product("product_2.json")
    assert "https://www.fluke.com/en/product/electrical-testing/digital-multimeters/fluke-117" in source
    for name in product.specs:
        assert f"`specs.{name}`" in source
    assert "`name`" in source
    assert "`manufacturer`" in source
    assert "`description`" in source


def test_generated_results_have_real_drafts_meeting_copy_limits() -> None:
    results = (ROOT / "examples" / "generated_results.md").read_text(encoding="utf-8")
    assert "Модель: `qwen3:8b`" in results
    assert "реальными вызовами локальной модели" in results
    payloads = re.findall(r"```json\n(.*?)\n```", results, flags=re.DOTALL)
    assert len(payloads) == 2
    for payload in payloads:
        draft = json.loads(payload)
        assert 1 <= len(draft["seo_title"]) <= 70
        assert 800 <= len(draft["seo_description"]) <= 1200
        assert 3 <= len(draft["search_queries"]) <= 5
        assert draft["characteristics"]
