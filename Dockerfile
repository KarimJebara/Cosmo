# syntax=docker/dockerfile:1.7

# ---- builder stage: install deps into a virtualenv ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build deps for argon2-cffi (libffi) and rapidfuzz wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt ./requirements/base.txt
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements/base.txt


# ---- runtime stage: minimal image with the venv copied over ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    COSMO_DATA_DIR=/data \
    DATABASE_URL=sqlite:////data/budget_tracker.db

# Non-root user.
RUN groupadd --system cosmo && useradd --system --gid cosmo --home /app cosmo

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=cosmo:cosmo . /app

# Persistent volume for the SQLite DB and any uploaded CSVs.
RUN mkdir -p /data && chown -R cosmo:cosmo /data

USER cosmo

EXPOSE 5002

# Healthcheck hits the /healthz endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:5002/healthz', timeout=3).status == 200 else sys.exit(1)"

# Entrypoint: migrate then exec gunicorn. `exec` keeps PID 1 = gunicorn so
# Docker SIGTERM reaches the workers.
CMD ["sh", "-c", "python cli.py init-db && exec gunicorn -w ${GUNICORN_WORKERS:-2} -b 0.0.0.0:5002 --access-logfile - --error-logfile - wsgi:app"]
