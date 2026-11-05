"""Markdown rendering tests including dynamic-value escaping."""

from app.schemas import Characteristic, ProductDraft
from app.services.renderer import render_markdown


def _draft(**overrides: object) -> ProductDraft:
    values: dict[str, object] = {
        "seo_title": "Манометр DM 02",
        "seo_description": "Краткое описание прибора.",
        "characteristics": [Characteristic(name="Диапазон", value="0–1,6 МПа")],
        "search_queries": ["манометр DM 02", "Манотомь DM 02", "прибор для давления"],
        "commercial_block": "Для измерения давления.",
        "missing_data": ["Производитель: данных нет"],
        "warnings": ["Проверьте число 42 вручную."],
    }
    values.update(overrides)
    return ProductDraft.model_validate(values)


def test_renderer_includes_all_fields_and_sections() -> None:
    markdown = render_markdown(_draft())

    for heading in (
        "## SEO-заголовок",
        "## SEO-описание",
        "## Ключевые характеристики",
        "## Поисковые запросы",
        "## Коммерческий блок",
        "## Отсутствующие данные",
        "## Предупреждения",
    ):
        assert heading in markdown
    assert "**Диапазон**" in markdown
    assert "0–1,6 МПа" in markdown
    assert "Производитель: данных нет" in markdown
    assert r"Проверьте число 42 вручную\." in markdown


def test_renderer_shows_empty_characteristics_and_empty_lists() -> None:
    draft = _draft(characteristics=[], missing_data=[], warnings=[])

    markdown = render_markdown(draft)

    assert "## Ключевые характеристики\n\nДанных нет." in markdown
    assert "## Отсутствующие данные\n\nНет." in markdown
    assert "## Предупреждения\n\nНет." in markdown


def test_renderer_escapes_markdown_special_characters_in_dynamic_values() -> None:
    draft = _draft(
        seo_title="# Заголовок *курсив* [ссылка](https://bad.test)",
        characteristics=[Characteristic(name="*Параметр*", value="`код` | <тег>")],
        search_queries=["[запрос]", "обычный запрос", "ещё запрос"],
        commercial_block="Строка\n# не заголовок и **не жирный**",
    )

    markdown = render_markdown(draft)

    assert r"\# Заголовок \*курсив\* \[ссылка\]\(https://bad\.test\)" in markdown
    assert r"\*Параметр\*" in markdown
    assert r"\`код\` \| \<тег\>" in markdown
    assert r"\# не заголовок и \*\*не жирный\*\*" in markdown
