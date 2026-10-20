# Hardened Non-Root Disposable Sandbox Execution Container (Sections 14, 15, 45)
FROM python:3.12.7-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONNOUSERSITE=1

RUN groupadd -r sandbox && useradd -r -g sandbox -d /sandbox -s /sbin/nologin sandbox \
    && mkdir -p /sandbox && chown -R sandbox:sandbox /sandbox

WORKDIR /sandbox
COPY pyforge/sandbox /sandbox/pyforge/sandbox
USER sandbox

HEALTHCHECK --interval=20s --timeout=3s --retries=3 \
  CMD python3 -I -c "print('sandbox_ok')" || exit 1

ENTRYPOINT ["python3", "-I", "-B"]
