# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

# Prevent interactive tzdata, speed pip, no cache
ENV PIP_NO_INPUT=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# --- deps layer: copy only manifests to preserve cache
# Copy requirements files first for better layer caching
COPY requirements.txt /app/worker/requirements.txt

# Install deps with BuildKit cache mount for faster rebuilds
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --upgrade pip wheel && \
    pip install --no-cache-dir -r /app/worker/requirements.txt && \
    pip install --no-cache-dir python-multipart

# --- app layer: copy source last (invalidates less)
COPY . /app/worker

EXPOSE 8090

HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD ["python","-c","import urllib.request,sys; \
d=urllib.request.urlopen('http://localhost:8090/health',timeout=2).read(); \
sys.exit(0 if b'{\\\"ok\\\":true' in d else 1)"]

CMD ["uvicorn", "worker.app.main:app", "--host", "0.0.0.0", "--port", "8090"]
