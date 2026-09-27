FROM python:3.12-slim

# System security & optimization flags
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies needed for compilation / postgres client
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application and Alembic files
COPY . .
RUN chmod +x start.sh

# Run as non-privileged user
RUN useradd -u 1000 -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000 10000

# Default command executes migration, background worker, and FastAPI server
CMD ["./start.sh"]
