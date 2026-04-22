# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[mcp]"

ENV HOST=0.0.0.0 \
    PORT=8080 \
    THEOGONY_LLM__PROVIDER=stub

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request, sys; p=os.environ.get('PORT','8080'); urllib.request.urlopen(f'http://127.0.0.1:{p}/health', timeout=3); sys.exit(0)" || exit 1

ENTRYPOINT ["sh", "-c", "exec theogony mcp --transport sse --seed --host \"${HOST:-0.0.0.0}\" --port \"${PORT:-8080}\""]
