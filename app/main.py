"""FastAPI application entry point; generation endpoint is a scaffold for now."""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.schemas import ProductInput

app = FastAPI(title="Генератор карточек товаров", version="0.1.0")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the starter form."""
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.get("/health")
async def health() -> dict[str, str]:
    """Report process availability without contacting the LLM provider."""
    return {"status": "ok"}


@app.post("/api/products/draft")
async def create_draft(product: ProductInput) -> None:
    """TODO: call DraftService and return DraftResponse."""
    del product
    raise HTTPException(status_code=501, detail="Генерация черновика ещё не реализована")
