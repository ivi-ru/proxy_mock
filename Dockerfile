ARG PYTHON_VERSION=3.14-slim
FROM python:${PYTHON_VERSION} AS base

# --- Dependency build stage (compilers live only here) ---
FROM base AS builder

RUN apt-get update \
&& apt-get install -y --no-install-recommends build-essential gcc git \
&& rm -rf /var/lib/apt/lists/* \
&& python -m pip install --upgrade pip setuptools wheel \
&& pip install uv==0.11.26

# copy: otherwise uv complains about hardlinks across layers; never: use the base image interpreter.
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /build
COPY pyproject.toml uv.lock ./

# IMPORTANT: a venv cannot be moved to a different path, because console scripts hardcode the
# absolute interpreter path in their shebang. So the final stage copies the venv to the SAME path.
RUN UV_PROJECT_ENVIRONMENT=/opt/venv-main uv sync --locked --no-install-project --no-dev

# --- Final slim server image ---
FROM base AS runtime

COPY --from=builder /opt/venv-main /opt/venv-main
ENV PATH="/opt/venv-main/bin:$PATH"
ENV PYTHONPATH=/var/www/proxy_mock

WORKDIR /var/www/proxy_mock
# pyproject.toml is read at runtime to determine the service version
COPY pyproject.toml ./
COPY proxy_mock ./proxy_mock

ARG CMD_ARG=""
ENV CMD_ARG=${CMD_ARG}

CMD ${CMD_ARG}
