"""Generate and save real local-model results for the checked-in product examples.

Run from the repository root with Ollama available at OLLAMA_BASE_URL, e.g.:
OLLAMA_BASE_URL=http://host.docker.internal:11434 python -m scripts.generate_examples
"""

import asyncio
import json
from datetime import date
from pathlib import Path

from app.config import settings
from app.schemas import ProductInput
from app.services.draft_service import DraftService, DraftValidationError
from app.services.llm_client import LLMClient, LLMError
from app.services.renderer import render_markdown

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_FILES = ("product_1.json", "product_2.json")


async def generate_report() -> str:
    """Generate both drafts before returning a report, avoiding partial/fake results."""
    service = DraftService(LLMClient(settings))
    sections: list[str] = [
        "# Фактические результаты генерации Ollama",
        "",
        f"Дата генерации: {date.today().isoformat()}",
        f"Модель: `{settings.ollama_model}`",
        "",
        "Все текстовые поля ниже получены реальными вызовами локальной модели и являются",
        "черновиками. Контент-менеджер должен проверить их перед публикацией.",
        "Числовой валидатор не проверяет семантическую достоверность утверждений.",
        "",
    ]

    for index, filename in enumerate(PRODUCT_FILES, start=1):
        product_path = ROOT / "examples" / filename
        product = ProductInput.model_validate_json(product_path.read_text(encoding="utf-8"))
        try:
            draft = await service.create_draft(product)
        except DraftValidationError as exc:
            raise DraftValidationError(
                [f"{filename}: {error}" for error in exc.errors]
            ) from None
        sections.extend(
            [
                f"## Товар {index}: {product.name}",
                "",
                f"Файл источника: `{filename}`",
                (
                    f"Длина SEO-заголовка: {len(draft.seo_title)} символов; "
                    f"длина SEO-описания: {len(draft.seo_description)} символов; "
                    f"поисковых запросов: {len(draft.search_queries)}."
                ),
                "",
                render_markdown(draft),
                "",
                "### JSON-ответ",
                "",
                "```json",
                json.dumps(draft.model_dump(mode="json"), ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
    return "\n".join(sections).rstrip() + "\n"


async def main() -> None:
    """Write results only after both live generations succeed."""
    if not settings.ollama_model:
        raise SystemExit("Не задан OLLAMA_MODEL; файл результатов не изменён.")
    output_path = ROOT / "examples" / "generated_results.md"
    try:
        report = await generate_report()
    except DraftValidationError as exc:
        details = "; ".join(exc.errors)
        raise SystemExit(
            f"Реальная генерация не завершена (DraftValidationError: {details}); "
            "файл результатов не изменён."
        ) from None
    except LLMError as exc:
        raise SystemExit(
            f"Реальная генерация не завершена ({type(exc).__name__}); файл результатов не изменён."
        ) from None
    output_path.write_text(report, encoding="utf-8")
    print(f"Оба ответа модели сохранены: {output_path.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
