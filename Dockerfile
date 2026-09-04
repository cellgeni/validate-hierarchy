# syntax=docker/dockerfile:1

##############################
# Builder stage
##############################
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# uv configuration: copy (not hardlink) into the image, compile bytecode,
# and place the virtualenv at a predictable location inside the project.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Install dependencies first (cached layer) using only the lockfile + manifest,
# so application code changes don't invalidate the dependency layer.
# --all-extras pulls in python-irodsclient for the `irods` subcommand.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --all-extras

# Now copy the source and install the project itself.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY schema ./schema
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --all-extras

##############################
# Runtime stage
##############################
FROM python:3.12-slim-bookworm AS runtime

# procps provides `ps`, which Nextflow requires to collect task metrics.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        procps \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user.
RUN useradd --create-home --uid 1000 validate

WORKDIR /app

# Copy the fully-built virtualenv and the project source from the builder.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/schema /app/schema

# Put the virtualenv on PATH so the `validate-hierarchy` entry point is
# available. The example schemas are bundled under /app/schema but are not
# wired to a default: --schema is always explicit.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    VALIDATE_HIERARCHY_EMAIL_FROM="noreply-reprocessing@cellgeni-su"

USER validate

# No ENTRYPOINT: Nextflow invokes its own `.command.sh` via the shell and needs
# to run arbitrary commands (e.g. `validate-hierarchy`, `cat`, `ps`). A
# hardcoded ENTRYPOINT would be prepended to every command under the Docker
# executor.
CMD ["bash"]
