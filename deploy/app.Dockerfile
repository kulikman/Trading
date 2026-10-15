# Python-часть Earnings Engine (E9): миграции, планировщик, API дашборда — один образ.
FROM python:3.12-slim-bookworm
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 TZ=UTC
RUN pip install --no-cache-dir uv==0.11.9
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "core.scheduler"]
