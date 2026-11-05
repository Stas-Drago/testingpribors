"""FastAPI application and safe HTTP boundary for draft generation."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.schemas import DraftResponse, ProductInput
from app.services.draft_service import DraftService, DraftValidationError
from app.services.llm_client import (
    LLMConfigurationError,
    LLMProviderError,
    LLMRefusalError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.services.renderer import render_markdown

app = FastAPI(title="Генератор карточек товаров", version="0.1.0")
templates = Jinja2Templates(directory="app/templates")


def get_draft_service() -> DraftService:
    """Build the generation service per request; override this dependency in tests."""
    return DraftService()


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Avoid echoing submitted content in validation responses."""
    del request, exc
    return JSONResponse(
        status_code=422,
        content={"detail": "Некорректный JSON или структура входных данных"},
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the product content workspace."""
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/health")
async def health() -> dict[str, str]:
    """Report process availability without contacting OpenAI."""
    return {"status": "ok"}


@app.post("/api/products/draft", response_model=DraftResponse)
async def create_draft(
    product: ProductInput,
    service: Annotated[DraftService, Depends(get_draft_service)],
) -> DraftResponse:
    """Generate validated product copy and a copy-ready Markdown representation."""
    try:
        draft = await service.create_draft(product)
    except LLMTimeoutError as exc:
        raise _http_error(504, "Истекло время ожидания ответа OpenAI API") from exc
    except (LLMConfigurationError, LLMUnavailableError) as exc:
        raise _http_error(503, "OpenAI API не настроен или сейчас недоступен") from exc
    except (LLMProviderError, LLMResponseError, LLMRefusalError, DraftValidationError) as exc:
        raise _http_error(502, "Не удалось получить корректный черновик от OpenAI API") from exc
    return DraftResponse(draft=draft, markdown=render_markdown(draft))


def _http_error(status_code: int, message: str) -> HTTPException:
    """Create a sanitized HTTP exception without provider details."""
    return HTTPException(status_code=status_code, detail=message)
