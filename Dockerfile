# syntax=docker/dockerfile:1

FROM node:24-bookworm-slim AS assets

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY static ./static
COPY shopman ./shopman
RUN npm run css:build && npm run gestor:build


FROM python:3.12-slim AS runtime

ENV DJANGO_SETTINGS_MODULE=config.settings \
    PATH="/home/shopman/.local/bin:${PATH}" \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system shopman \
    && adduser --system --ingroup shopman --home /home/shopman shopman \
    && apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md manage.py ./
COPY config ./config
COPY instances ./instances
COPY packages ./packages
COPY shopman ./shopman

COPY --from=assets /app/shopman/storefront/static/storefront/css/output.css \
    ./shopman/storefront/static/storefront/css/output.css
COPY --from=assets /app/shopman/storefront/static/storefront/css/output-gestor.css \
    ./shopman/storefront/static/storefront/css/output-gestor.css

RUN python -m pip install --upgrade pip \
    && python -m pip install \
        ./packages/refs \
        ./packages/utils \
        ./packages/offerman \
        ./packages/stockman \
        ./packages/craftsman \
        ./packages/guestman \
        ./packages/doorman \
        ./packages/orderman \
        ./packages/payman \
        .

RUN mkdir -p /app/staticfiles /app/media \
    && chown -R shopman:shopman /app /home/shopman

USER shopman

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health/" >/dev/null || exit 1

CMD daphne -b 0.0.0.0 -p "${PORT}" config.asgi:application
