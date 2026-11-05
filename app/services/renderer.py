"""Render a validated draft as Markdown for copying."""

import re

from app.schemas import ProductDraft

_MARKDOWN_SPECIALS = re.compile(r"([\\`*_{}\[\]<>()#+\-.!|~])")


def _escape_markdown(value: str) -> str:
    """Escape Markdown syntax in dynamic values while leaving line breaks intact."""
    return _MARKDOWN_SPECIALS.sub(r"\\\1", value)


def render_markdown(draft: ProductDraft) -> str:
    """Format every draft field with stable Russian headings and escaped values."""
    lines = [
        "# Черновик карточки товара",
        "",
        "## SEO-заголовок",
        "",
        _escape_markdown(draft.seo_title),
        "",
        "## SEO-описание",
        "",
        _escape_markdown(draft.seo_description),
        "",
        "## Ключевые характеристики",
        "",
    ]

    if draft.characteristics:
        lines.extend(
            f"- **{_escape_markdown(item.name)}** — {_escape_markdown(item.value)}"
            for item in draft.characteristics
        )
    else:
        lines.append("Данных нет.")

    lines.extend(["", "## Поисковые запросы", ""])
    lines.extend(f"- {_escape_markdown(query)}" for query in draft.search_queries)
    lines.extend(["", "## Коммерческий блок", "", _escape_markdown(draft.commercial_block)])
    lines.extend(["", "## Отсутствующие данные", ""])
    lines.extend(f"- {_escape_markdown(item)}" for item in draft.missing_data)
    if not draft.missing_data:
        lines.append("Нет.")

    lines.extend(["", "## Предупреждения", ""])
    lines.extend(f"- {_escape_markdown(item)}" for item in draft.warnings)
    if not draft.warnings:
        lines.append("Нет.")

    return "\n".join(lines)
