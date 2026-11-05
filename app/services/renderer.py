"""Render a validated draft as Markdown for copying."""

from app.schemas import ProductDraft


def render_markdown(draft: ProductDraft) -> str:
    """TODO: format every output field in readable Russian Markdown."""
    del draft
    raise NotImplementedError("Markdown-рендерер ещё не реализован")
