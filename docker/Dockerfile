# syntax=docker/dockerfile:1.7
#
# DeckBridge container image. Two-stage build:
#   1. node — compile the SvelteKit SPA into static assets
#   2. python — install backend, bundle in the built assets, run as non-root
#
# Built locally only in v1 (no registry publishing). Run from the repo root:
#   docker compose -f docker/docker-compose.yml up -d --build

# ---------- Stage 1: frontend ----------
FROM node:22-alpine AS frontend
WORKDIR /work
COPY web/package.json web/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY web/ ./
# svelte.config.js writes the build output to ../src/deckbridge/web_dist
# so we mirror that path inside the build context.
RUN mkdir -p /work-out && npm run build

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DECKBRIDGE_DATA_DIR=/data \
    DECKBRIDGE_PORT=7878

# System libraries the StreamDeck library and image stack need at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libhidapi-libusb0 \
        libudev1 \
        libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user, owns the persistent data volume.
RUN useradd --system --uid 1000 --create-home --home-dir /home/deckbridge deckbridge \
    && mkdir -p /data \
    && chown -R deckbridge:deckbridge /data

WORKDIR /app

# Copy backend source and the built frontend assets.
COPY --chown=deckbridge:deckbridge pyproject.toml README.md LICENSE ./
COPY --chown=deckbridge:deckbridge src/ ./src/
COPY --from=frontend --chown=deckbridge:deckbridge /src/deckbridge/web_dist /app/src/deckbridge/web_dist

RUN pip install --no-cache-dir .

USER deckbridge
EXPOSE 7878
VOLUME ["/data"]

CMD ["deckbridge", "run"]
