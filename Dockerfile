FROM python:3.14-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

COPY shop ./shop


FROM python:3.14-slim

LABEL org.opencontainers.image.source="https://github.com/Pranshu-Raj/SLO-Driven-Observability-Stack"
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=build /app /app

ARG VERSION=dev
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_VERSION=$VERSION

USER 10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "shop"]
CMD ["api"]
