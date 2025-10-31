# Base stage - dependency installation
FROM python:3.10-slim AS base

WORKDIR /app

# Install system dependencies (curl for health checks, procps for debugging)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application stage
FROM base

WORKDIR /app

# Copy application code
COPY . .

# Copy data scripts to separate directory (volume mount won't overlay these)
RUN mkdir -p /app/scripts && \
    cp data/get_daily_price.py /app/scripts/ && \
    cp data/get_interdaily_price.py /app/scripts/ && \
    cp data/merge_jsonl.py /app/scripts/

# Create necessary directories
RUN mkdir -p data logs data/agent_data

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Expose API server port (MCP services are internal only)
EXPOSE 8080

# Set Python to run unbuffered for real-time logs
ENV PYTHONUNBUFFERED=1

# Use API entrypoint script (no CMD needed - FastAPI runs as service)
ENTRYPOINT ["./entrypoint.sh"]
