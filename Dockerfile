# Base stage - dependency installation
FROM python:3.10-slim as base

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application stage
FROM base

WORKDIR /app

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p data logs data/agent_data

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Expose MCP service ports and web dashboard
EXPOSE 8000 8001 8002 8003 8888

# Set Python to run unbuffered for real-time logs
ENV PYTHONUNBUFFERED=1

# Use entrypoint script
ENTRYPOINT ["./entrypoint.sh"]
CMD ["configs/default_config.json"]
