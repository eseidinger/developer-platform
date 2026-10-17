FROM node:24.14.0-alpine AS ui-builder
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM node:22.22.0-bookworm-slim@sha256:dd9d21971ec4395903fa6143c2b9267d048ae01ca6d3ea96f16cb30df6187d94 AS store-console-assets
WORKDIR /console
ADD --checksum=sha256:a9ba3df8555df4d4f73598250e14cd5d773cef1307528aa58a1317cf1d46adc0 https://github.com/rustfs/console/archive/ec3ddbe8121bfa8376bcb35781a6d4e703bca607.tar.gz /source.tar.gz
RUN tar -xzf /source.tar.gz --strip-components=1 -C /console && rm /source.tar.gz
COPY consoles/patch-rustfs.cjs /patch-rustfs.cjs
RUN node /patch-rustfs.cjs && npm install --global pnpm@12.3.4 && pnpm install --frozen-lockfile
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm type-check && pnpm lint && pnpm format:check && pnpm test:run && pnpm build
COPY consoles/rustfs.json /console/out/platform-console-pin.json
COPY consoles/LICENSE.rustfs-console /console/out/LICENSE.rustfs-console
COPY consoles/NOTICE.rustfs-console /console/out/NOTICE.rustfs-console

FROM scratch AS store-console-export
COPY --from=store-console-assets /console/out/ /rustfs/

FROM python:3.14.7-slim-trixie
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.17 /uv /uvx /bin/
COPY app/pyproject.toml app/uv.lock app/README.md ./
COPY app/src ./src
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home platform
RUN mkdir -p /var/lib/platform-monitoring && chown 10001:10001 /var/lib/platform-monitoring
COPY --from=ui-builder /ui/dist/ ./src/app/static/
COPY --from=store-console-assets /console/out/ ./store-consoles/rustfs/
USER 10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
