FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.7.11 /uv /uvx /bin/

WORKDIR /mastr

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

COPY . /mastr

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-editable



FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y curl unzip && \
    apt-get clean

USER 1000:1000

COPY --from=builder /mastr /mastr
ENTRYPOINT ["/mastr/scheduler.py"]
