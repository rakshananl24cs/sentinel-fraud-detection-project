# ==============================================================================
# DOCKERFILE: Cost-Sensitive Fraud Detection API
# Base: Python 3.12 Slim (Debian Bookworm)
# ==============================================================================

FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MODEL_DIR=/app/ml/models

WORKDIR /app

# Install minimal OS dependencies:
# - libgomp1: required for OpenMP parallel processing in XGBoost and scikit-learn
# - curl: required for Docker container health check probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pinned Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create dedicated non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy application source code and runtime model artifacts
# Note: Raw datasets, tests, notebooks, and secrets are excluded via .dockerignore
COPY backend /app/backend
COPY ml/src /app/ml/src
COPY ml/models /app/ml/models
COPY alembic.ini /app/alembic.ini
COPY database /app/database

# Adjust ownership to non-root user
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Docker health probe evaluating API process liveness
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Start uvicorn server running FastAPI entrypoint
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
