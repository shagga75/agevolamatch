FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# The venv built above already matches the lockfile; skip uv re-syncing
# (which would otherwise pull the dev dependency group) on every `uv run`.
ENV UV_NO_SYNC=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "agevolamatch.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
