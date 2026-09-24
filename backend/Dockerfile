# ── SupportNova backend ───────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: build tools for argon2/psycopg wheels that lack a slim wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# The dataset is a sibling of backend/ in the repository, so it is not part of
# this build context. Documents are ingested into the database rather than read
# from disk at runtime, so the image does not need it -- but the render script
# and the test suite do. Mount it, or set DATASET_DIR, when you need either.
ENV DATASET_DIR=/app/dataset

RUN mkdir -p var/uploads reports/generated

EXPOSE 8000

# Migrate, then serve.  Seeding is a separate explicit step so a redeploy never
# silently resets evaluator data.
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
