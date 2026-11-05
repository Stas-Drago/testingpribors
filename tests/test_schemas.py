"""Tests for input normalization and public Pydantic contracts."""

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.schemas import Characteristic, DraftResponse, ProductDraft, ProductInput


def test_valid_product_preserves_source_values() -> None:
    product = ProductInput(
        name=" Манометр DM 02 ",
        manufacturer=" Манотомь ",
        specs={"Диапазон": "0–1,6 МПа"},
        description="Измерение давления",
    )

    assert product.name == "Манометр DM 02"
    assert product.manufacturer == "Манотомь"
    assert product.specs == {"Диапазон": "0–1,6 МПа"}
    assert product.description == "Измерение давления"


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_blank_product_name_is_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="Название товара"):
        ProductInput(name=name)


def test_missing_product_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProductInput.model_validate({"manufacturer": "Манотомь"})


def test_optional_blank_text_is_normalized_to_none() -> None:
    product = ProductInput(name="DM 02", manufacturer="  ", description="\n")

    assert product.manufacturer is None
    assert product.description is None


@pytest.mark.parametrize("payload", [{"name": "DM 02"}, {"name": "DM 02", "specs": {}}])
def test_specs_can_be_missing_or_empty(payload: dict[str, object]) -> None:
    product = ProductInput.model_validate(payload)

    assert product.specs == {}


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "DM 02", "specs": []},
        {"name": "DM 02", "specs": {"Диапазон": 1.6}},
        {"name": "DM 02", "manufacturer": 42},
    ],
)
def test_invalid_field_types_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProductInput.model_validate(payload)


def test_extra_input_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ProductInput.model_validate({"name": "DM 02", "unknown": "value"})


def test_settings_allow_startup_without_local_model(monkeypatch) -> None:
    for name in (
        "OLLAMA_MODEL",
        "OLLAMA_BASE_URL",
        "LLM_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.ollama_model is None
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.llm_timeout_seconds == 30


def test_settings_read_ollama_values_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434/")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")

    settings = Settings(_env_file=None)

    assert settings.ollama_model == "qwen3:8b"
    assert settings.ollama_base_url == "http://ollama.test:11434/"
    assert settings.llm_timeout_seconds == 45


@pytest.mark.parametrize("timeout", ["0", "-1"])
def test_settings_reject_non_positive_timeout(monkeypatch, timeout: str) -> None:
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_output_contracts_accept_expected_payload() -> None:
    draft = ProductDraft(
        seo_title="Манометр DM 02",
        seo_description="Черновик описания",
        characteristics=[Characteristic(name="Диапазон", value="0–1,6 МПа")],
        search_queries=["манометр DM 02", "манометр для давления", "Манотомь DM 02"],
        commercial_block="Для задач, описанных в исходных данных.",
    )
    response = DraftResponse(draft=draft, markdown="# Черновик")

    assert response.draft.characteristics[0].value == "0–1,6 МПа"
    assert response.markdown == "# Черновик"
