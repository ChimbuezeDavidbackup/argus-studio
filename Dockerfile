# ==========================================
# Argus Studio - Universal Cloud Container
# ==========================================
FROM python:3.11-slim

# Prevent prompts and buffer lag
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies including FFmpeg for DASH stream muxing & MP3 conversion
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose default HTTP port
EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000

# Run Web & Mobile API Server
CMD ["python", "server.py"]
