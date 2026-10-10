# syntax=docker/dockerfile:1

FROM python:3.13-slim-bookworm AS builder
WORKDIR /build
COPY src/requirements.txt ./requirements.txt
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.13-slim-bookworm AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TIKTOK_DOWNLOAD_DIR=/app/downloads
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --home-dir /app app \
    && mkdir -p /app/downloads \
    && chown -R app:app /app
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index /wheels/*.whl \
    && rm -rf /wheels
USER app

FROM runtime-base AS test
COPY --chown=app:app src/ /app/src/
COPY --chown=app:app tests/ /app/tests/
RUN python -m unittest discover -s tests -v

FROM runtime-base AS runtime
# Copying from test makes a successful test run a prerequisite of the final image.
COPY --from=test --chown=app:app /app/src/ /app/src/
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).close()"]
CMD ["python", "-m", "uvicorn", "main:app", "--app-dir", "/app/src", "--host", "0.0.0.0", "--port", "8000"]
