FROM node:24.14.0-alpine AS ui-builder
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.14.7-slim-trixie
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/
COPY app/pyproject.toml app/uv.lock app/README.md ./
COPY app/src ./src
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home platform
RUN mkdir -p /var/lib/platform-monitoring && chown 10001:10001 /var/lib/platform-monitoring
COPY --from=ui-builder /ui/dist/ ./src/app/static/
USER 10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
