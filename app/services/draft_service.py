"""Orchestrate validation, LLM generation, deterministic fields, and rendering."""

from app.schemas import ProductDraft, ProductInput


class DraftService:
    """TODO: compose the LLM client, validator, and renderer."""

    async def create_draft(self, product: ProductInput) -> ProductDraft:
        """Generate one product draft from its source data."""
        raise NotImplementedError("DraftService ещё не реализован")
