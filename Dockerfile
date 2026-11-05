FROM python:3.13-slim

WORKDIR /workspace

COPY pyproject.toml ./
COPY app ./app
COPY tests ./tests

RUN python -m pip install --no-cache-dir -e ".[dev]"

COPY . .

CMD ["python", "-m", "pytest"]
