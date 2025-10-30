# Docker Deployment and CI/CD Design

**Date:** 2025-10-30
**Status:** Approved
**Target:** Development/local testing environment

## Overview

Package AI-Trader as a Docker container with docker-compose orchestration and automated image builds via GitHub Actions on release tags. Focus on simplicity and ease of use for researchers and developers.

## Requirements

- **Primary Use Case:** Development and local testing
- **Deployment Target:** Single monolithic container (all MCP services + trading agent)
- **Secrets Management:** Environment variables (no mounted .env file)
- **Data Strategy:** Fetch price data on container startup
- **Container Registry:** GitHub Container Registry (ghcr.io)
- **Trigger:** Build images automatically on release tag push (`v*` pattern)

## Architecture

### Components

1. **Dockerfile** - Builds Python 3.10 image with all dependencies
2. **docker-compose.yml** - Orchestrates container with volume mounts and environment config
3. **entrypoint.sh** - Sequential startup script (data fetch → MCP services → trading agent)
4. **GitHub Actions Workflow** - Automated image build and push on release tags
5. **.dockerignore** - Excludes unnecessary files from image
6. **Documentation** - Docker usage guide and examples

### Execution Flow

```
Container Start
    ↓
entrypoint.sh
    ↓
1. Fetch/merge price data (get_daily_price.py → merge_jsonl.py)
    ↓
2. Start MCP services in background (start_mcp_services.py)
    ↓
3. Wait 3 seconds for service stabilization
    ↓
4. Run trading agent (main.py with config)
    ↓
Container Exit → Cleanup MCP services
```

## Detailed Design

### 1. Dockerfile

**Multi-stage build:**

```dockerfile
# Base stage
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

# Expose MCP service ports
EXPOSE 8000 8001 8002 8003

# Set Python to run unbuffered
ENV PYTHONUNBUFFERED=1

# Use entrypoint script
ENTRYPOINT ["./entrypoint.sh"]
CMD ["configs/default_config.json"]
```

**Key Features:**
- `python:3.10-slim` base for smaller image size
- Multi-stage for dependency caching
- Non-root user NOT included (dev/testing focus, can add later)
- Unbuffered Python output for real-time logs
- Default config path with override support

### 2. docker-compose.yml

```yaml
version: '3.8'

services:
  ai-trader:
    build: .
    container_name: ai-trader-app
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - OPENAI_API_BASE=${OPENAI_API_BASE}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ALPHAADVANTAGE_API_KEY=${ALPHAADVANTAGE_API_KEY}
      - JINA_API_KEY=${JINA_API_KEY}
      - RUNTIME_ENV_PATH=/app/data/runtime_env.json
      - MATH_HTTP_PORT=${MATH_HTTP_PORT:-8000}
      - SEARCH_HTTP_PORT=${SEARCH_HTTP_PORT:-8001}
      - TRADE_HTTP_PORT=${TRADE_HTTP_PORT:-8002}
      - GETPRICE_HTTP_PORT=${GETPRICE_HTTP_PORT:-8003}
      - AGENT_MAX_STEP=${AGENT_MAX_STEP:-30}
    ports:
      - "8000:8000"
      - "8001:8001"
      - "8002:8002"
      - "8003:8003"
      - "8888:8888"  # Optional: web dashboard
    restart: unless-stopped
```

**Key Features:**
- Volume mounts for data/logs persistence
- Environment variables interpolated from `.env` file (Docker Compose reads automatically)
- No `.env` file mounted into container (cleaner separation)
- Default port values with override support
- Restart policy for recovery

### 3. entrypoint.sh

```bash
#!/bin/bash
set -e  # Exit on any error

echo "🚀 Starting AI-Trader..."

# Step 1: Data preparation
echo "📊 Fetching and merging price data..."
cd /app/data
python get_daily_price.py
python merge_jsonl.py
cd /app

# Step 2: Start MCP services in background
echo "🔧 Starting MCP services..."
cd /app/agent_tools
python start_mcp_services.py &
MCP_PID=$!
cd /app

# Step 3: Wait for services to initialize
echo "⏳ Waiting for MCP services to start..."
sleep 3

# Step 4: Run trading agent with config file
echo "🤖 Starting trading agent..."
CONFIG_FILE="${1:-configs/default_config.json}"
python main.py "$CONFIG_FILE"

# Cleanup on exit
trap "echo '🛑 Stopping MCP services...'; kill $MCP_PID 2>/dev/null" EXIT
```

**Key Features:**
- Sequential execution with clear logging
- MCP services run in background with PID capture
- Trap ensures cleanup on container exit
- Config file path as argument (defaults to `configs/default_config.json`)
- Fail-fast with `set -e`

### 4. GitHub Actions Workflow

**File:** `.github/workflows/docker-release.yml`

```yaml
name: Build and Push Docker Image

on:
  push:
    tags:
      - 'v*'  # Triggers on v1.0.0, v2.1.3, etc.
  workflow_dispatch:  # Manual trigger option

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract version from tag
        id: meta
        run: |
          VERSION=${GITHUB_REF#refs/tags/v}
          echo "version=$VERSION" >> $GITHUB_OUTPUT

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/ai-trader:${{ steps.meta.outputs.version }}
            ghcr.io/${{ github.repository_owner }}/ai-trader:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**Key Features:**
- Triggers on `v*` tags (e.g., `git tag v1.0.0 && git push origin v1.0.0`)
- Manual dispatch option for testing
- Uses `GITHUB_TOKEN` (automatically provided, no secrets needed)
- Builds with caching for faster builds
- Tags both version and `latest`
- Multi-platform support possible by adding `platforms: linux/amd64,linux/arm64`

### 5. .dockerignore

```
# Version control
.git/
.gitignore

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Environment and secrets
.env
.env.*
!.env.example

# Data files (fetched at runtime)
data/*.json
data/agent_data/
data/merged.jsonl

# Logs
logs/
*.log

# Runtime state
runtime_env.json

# Documentation (not needed in image)
*.md
docs/
!README.md

# CI/CD
.github/
```

**Purpose:**
- Reduces image size
- Keeps secrets out of image
- Excludes generated files
- Keeps only necessary source code and scripts

## Documentation Updates

### New File: docs/DOCKER.md

Create comprehensive Docker usage guide including:

1. **Quick Start**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   docker-compose up
   ```

2. **Configuration**
   - Required environment variables
   - Optional configuration overrides
   - Custom config file usage

3. **Usage Examples**
   ```bash
   # Run with default config
   docker-compose up

   # Run with custom config
   docker-compose run ai-trader configs/my_config.json

   # View logs
   docker-compose logs -f

   # Stop and clean up
   docker-compose down
   ```

4. **Data Persistence**
   - How volume mounts work
   - Where data is stored
   - How to backup/restore

5. **Troubleshooting**
   - MCP services not starting → Check logs, verify ports available
   - Missing API keys → Check .env file
   - Data fetch failures → API rate limits or invalid keys
   - Permission issues → Volume mount permissions

6. **Using Pre-built Images**
   ```bash
   docker pull ghcr.io/hkuds/ai-trader:latest
   docker run --env-file .env -v $(pwd)/data:/app/data ghcr.io/hkuds/ai-trader:latest
   ```

### Update .env.example

Add/clarify Docker-specific variables:

```bash
# AI Model API Configuration
OPENAI_API_BASE=https://your-openai-proxy.com/v1
OPENAI_API_KEY=your_openai_key

# Data Source Configuration
ALPHAADVANTAGE_API_KEY=your_alpha_vantage_key
JINA_API_KEY=your_jina_api_key

# System Configuration (Docker defaults)
RUNTIME_ENV_PATH=/app/data/runtime_env.json

# MCP Service Ports
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003

# Agent Configuration
AGENT_MAX_STEP=30
```

### Update Main README.md

Add Docker section after "Quick Start":

```markdown
## Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Setup environment
cp .env.example .env
# Edit .env with your API keys

# Run with docker-compose
docker-compose up
```

### Using Pre-built Images

```bash
# Pull latest image
docker pull ghcr.io/hkuds/ai-trader:latest

# Run container
docker run --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  ghcr.io/hkuds/ai-trader:latest
```

See [docs/DOCKER.md](docs/DOCKER.md) for detailed Docker usage guide.
```

## Release Process

### For Maintainers

1. **Prepare release:**
   ```bash
   # Ensure main branch is ready
   git checkout main
   git pull origin main
   ```

2. **Create and push tag:**
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. **GitHub Actions automatically:**
   - Builds Docker image
   - Tags with version and `latest`
   - Pushes to `ghcr.io/hkuds/ai-trader`

4. **Verify build:**
   - Check Actions tab for build status
   - Test pull: `docker pull ghcr.io/hkuds/ai-trader:v1.0.0`

5. **Optional: Create GitHub Release**
   - Add release notes
   - Include Docker pull command

### For Users

```bash
# Pull specific version
docker pull ghcr.io/hkuds/ai-trader:v1.0.0

# Or always get latest
docker pull ghcr.io/hkuds/ai-trader:latest
```

## Implementation Checklist

- [ ] Create Dockerfile with multi-stage build
- [ ] Create docker-compose.yml with volume mounts and environment config
- [ ] Create entrypoint.sh with sequential startup logic
- [ ] Create .dockerignore to exclude unnecessary files
- [ ] Create .github/workflows/docker-release.yml for CI/CD
- [ ] Create docs/DOCKER.md with comprehensive usage guide
- [ ] Update .env.example with Docker-specific variables
- [ ] Update main README.md with Docker deployment section
- [ ] Test local build: `docker-compose build`
- [ ] Test local run: `docker-compose up`
- [ ] Test with custom config
- [ ] Verify data persistence across container restarts
- [ ] Test GitHub Actions workflow (create test tag)
- [ ] Verify image pushed to ghcr.io
- [ ] Test pulling and running pre-built image
- [ ] Update CLAUDE.md with Docker commands

## Future Enhancements

Possible improvements for production use:

1. **Multi-container Architecture**
   - Separate containers for each MCP service
   - Better isolation and independent scaling
   - More complex orchestration

2. **Security Hardening**
   - Non-root user in container
   - Docker secrets for production
   - Read-only filesystem where possible

3. **Monitoring**
   - Health checks for MCP services
   - Prometheus metrics export
   - Logging aggregation

4. **Optimization**
   - Multi-platform builds (ARM64 support)
   - Smaller base image (alpine)
   - Layer caching optimization

5. **Development Tools**
   - docker-compose.dev.yml with hot reload
   - Debug container with additional tools
   - Integration test container

These are deferred to keep initial implementation simple and focused on development/testing use cases.
