# ─── ETA Predictor – Lightweight Production Image ────────────────────────────
# Build:  docker build -t eta-predictor .
# Run:    docker run -p 5050:5050 eta-predictor
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.10-slim

WORKDIR /app

# System deps (none needed for lightweight mode)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY *.py ./
COPY paper.tex ./

# Create output dirs
RUN mkdir -p data outputs outputs/figures cache

# Run the full training pipeline at build time so the image ships
# with pre-trained models, figures, and the populated paper.tex.
RUN python main.py

# Expose API port
EXPOSE 5050

# Production WSGI server
CMD ["gunicorn", "--bind", "0.0.0.0:5050", "--workers", "2", "--timeout", "120", "app:app"]
