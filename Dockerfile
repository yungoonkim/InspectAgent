# ==============================================================================
# VisionInsight - Cloud Run CPU Production Dockerfile
# ==============================================================================
# Base Image: Minimal official Python 3.11 slim (Debian-based)
FROM python:3.11-slim

# System configuration & environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    ENVIRONMENT=production \
    HF_HUB_OFFLINE=1 \
    ENABLE_PATCHCORE=true \
    PATCHCORE_DEVICE=cpu \
    PATCHCORE_CHECKPOINT_PATH=models/patchcore/patchcore_bottle.ckpt \
    PATCHCORE_METADATA_PATH=models/patchcore/model_metadata.json \
    DECISION_THRESHOLD=34.1442

WORKDIR /app

# Install minimal OS dependencies for OpenCV headless and libgomp
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install production Python dependencies (CPU-only PyTorch, Anomalib, FastAPI)
COPY requirements-prod.txt .
RUN pip install --no-cache-dir --upgrade pip && \

    pip install --no-cache-dir -r requirements-prod.txt

# Copy application source code and verified PatchCore model artifacts
COPY backend/ ./backend/
COPY models/patchcore/patchcore_bottle.ckpt ./models/patchcore/
COPY models/patchcore/model_metadata.json ./models/patchcore/

# Create runtime directories for output images and inspection logs
RUN mkdir -p data/outputs data/logs

# Cloud Run dynamic PORT binding
EXPOSE 8080

# Production ASGI server launch (No --reload, 0.0.0.0 binding, PORT env substitution)
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
