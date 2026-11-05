"""Validate model output and build source-backed technical characteristics."""

from app.schemas import Characteristic, ProductInput


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


def validate_generated_copy(copy: dict[str, object]) -> list[str]:
    """TODO: validate lengths, query count, output types, and unsupported numeric claims."""
    del copy
    raise NotImplementedError("Проверка текста модели ещё не реализована")
