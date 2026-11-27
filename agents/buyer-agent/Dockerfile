FROM ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa AS uv
FROM python:3.11.16-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84 AS builder

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY . /app
# Windows Docker contexts may mark every source file executable.
RUN find /app/src -type f -exec chmod 0644 {} +
RUN uv --version \
    && test "$(uv --version | cut -d ' ' -f 2)" = "0.11.28" \
    && python scripts/verify_framework_wheels.py \
    && uv lock --check \
    && uv sync --frozen --no-dev --no-editable \
    && uv pip check \
    && uv build --wheel --out-dir /app/.agent-wheel \
    && uv pip install --python /app/.venv/bin/python --reinstall --no-deps /app/.agent-wheel/*.whl \
    && uv pip check \
    && find /app/.venv -type f -name '*.pyc' -delete \
    && .venv/bin/python -I -B scripts/enable_database.py --installed \
        --output /app/cogit.database.yaml \
    && .venv/bin/python -I -B scripts/worker_cohort.py prepare --root /app \
        --manifest /app/cogit.yaml --agent-wheel-dir /app/.agent-wheel \
        --output /app/worker-cohort \
    && .venv/bin/python -I -B scripts/worker_cohort.py prepare --root /app \
        --manifest /app/cogit.database.yaml --agent-wheel-dir /app/.agent-wheel \
        --output /app/database-worker-cohort \
    && .venv/bin/python -I -B scripts/verify_installed_packages.py \
        --agent-wheel-dir /app/.agent-wheel \
    && test -z "$(find /app/.venv -type f -name '*.pyc' -print -quit)"

FROM python:3.11.16-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/worker-cohort /app/worker-cohort
COPY --from=builder /app/database-worker-cohort /app/database-worker-cohort
COPY cogit.yaml /app/cogit.yaml
COPY evals /app/evals
COPY scripts/start_database_worker.sh /app/scripts/start_database_worker.sh
RUN useradd --create-home --uid 10001 agent
USER agent
CMD ["sh", "/app/scripts/start_database_worker.sh"]
