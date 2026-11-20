FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
COPY --chown=10001:10001 . .
RUN --mount=type=secret,id=package_ca \
    set -eu; groupadd --gid 10001 medexa && useradd --uid 10001 --gid 10001 --no-create-home medexa; \
    if [ -f /run/secrets/package_ca ]; then export SSL_CERT_FILE=/run/secrets/package_ca; fi; \
    uv sync --frozen --no-dev --no-editable && uv cache clean
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--no-proxy-headers"]

FROM runtime AS test
USER root
RUN --mount=type=secret,id=package_ca \
    set -eu; if [ -f /run/secrets/package_ca ]; then export SSL_CERT_FILE=/run/secrets/package_ca; fi; \
    uv sync --frozen --no-editable && uv cache clean
USER 10001:10001
CMD ["sh", "scripts/check.sh"]
