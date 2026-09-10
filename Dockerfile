# Stage 1: shared library layer — identical across all bfabric webapps.
# Cached as a single OCI blob on /misc/container/oci/; bump only when
# bfabric-web-apps itself is updated.
FROM python:3.12-slim AS libs
RUN pip install --no-cache-dir "bfabric-web-apps==0.9.8"

# Stage 2: app-specific deps on top of the shared layer (~5-20 MB unique per app).
FROM libs AS base

RUN groupadd --system appuser && useradd --system --gid appuser appuser

WORKDIR /app

COPY pyproject.toml .
# Install the app and its dependencies. bfabric-web-apps and its own deps are
# already present from the shared libs layer, so pip reuses them (no re-download);
# only the app's extra dependencies are fetched. Do NOT add --no-deps here — that
# silently skips app-declared deps (pandas, numpy, …) and the image only fails at
# runtime with an ImportError.
RUN pip install --no-cache-dir .

COPY index.py ./
COPY pyproject.toml ./
COPY utils/ utils/
RUN mkdir -p /tmp/flask_sessions && chown appuser:appuser /tmp/flask_sessions

ENV BFABRIC_WEBAPP_ENV=/app/.env \
    BFABRIC_WEBAPP_ENV_PREFIX=DRAUGRUI_

EXPOSE 8050

USER appuser

FROM base AS web
CMD sh -c 'exec gunicorn \
    --workers "${DRAUGRUI_GUNICORN_WORKERS:-4}" \
    --threads "${DRAUGRUI_GUNICORN_THREADS:-2}" \
    --bind "0.0.0.0:8050" \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    "index:server"'
