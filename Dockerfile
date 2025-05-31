# Dockerfile for manually create a planetai_llm_server image
# The Dockerfile uses a 2-tier approach, the files and configuratione (e.g. auth-codes/passwords) are not part of the final image
# 2024 PLANET AI GmbH, MSt
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /mastr

RUN apt-get update && apt-get install -y curl && apt-get clean


# install dependencies - cache aware
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

COPY . /mastr

# sync project - cache aware
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-editable



FROM python:3.13-slim

COPY --from=builder /mastr /mastr
ENTRYPOINT ["/mastr/download-mastr.sh"]
