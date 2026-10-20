# Multi-Stage Production Dockerfile for PyForge API (Section 45)
FROM python:3.12.7-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd -r pyforge && useradd -r -g pyforge -d /app -s /sbin/nologin pyforge
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pyforge /app/pyforge
COPY packages/curriculum /app/packages/curriculum
COPY database/migrations /app/database/migrations

RUN chown -R pyforge:pyforge /app
USER pyforge

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["uvicorn", "pyforge.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
