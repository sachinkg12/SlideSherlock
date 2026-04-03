FROM python:3.11-slim

# System deps for pipeline
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-nogui \
    ffmpeg \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONPATH=/app:/app/packages/core
