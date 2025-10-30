# Docker Deployment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Package AI-Trader as a Docker container with docker-compose orchestration and automated CI/CD builds on release tags.

**Architecture:** Single monolithic container running all MCP services and trading agent sequentially via entrypoint script. Environment variables injected via docker-compose. Price data fetched on startup. GitHub Actions builds and pushes images to ghcr.io on release tags.

**Tech Stack:** Docker, Docker Compose, Bash, GitHub Actions, Python 3.10

---

## Task 1: Create .dockerignore

**Files:**
- Create: `.dockerignore`

**Step 1: Create .dockerignore file**

Create `.dockerignore` in project root:

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
.venv/

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
data/merged_daily.jsonl
data/merged_hour.jsonl

# Logs
logs/
*.log

# Runtime state
runtime_env.json
.runtime_env.json

# Documentation (not needed in image)
docs/
!README.md

# CI/CD
.github/

# Git worktrees
.worktrees/

# Test files
test.py
delete.py
refresh_data.sh

# Build artifacts
build/
dist/
*.egg-info/
```

**Step 2: Verify file excludes data and secrets**

Run: `cat .dockerignore | grep -E "\.env|data/.*\.json|\.git"`
Expected: Should show .env, data/*.json, .git/ lines

**Step 3: Commit**

```bash
git add .dockerignore
git commit -m "Add .dockerignore for Docker builds

Excludes git history, Python cache, secrets, and runtime data"
```

---

## Task 2: Create Dockerfile

**Files:**
- Create: `Dockerfile`

**Step 1: Create Dockerfile with multi-stage build**

Create `Dockerfile` in project root:

```dockerfile
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
```

**Step 2: Verify Dockerfile syntax**

Run: `docker build --dry-run . 2>&1 | grep -i error || echo "Syntax OK"`
Expected: "Syntax OK" (or no critical errors)

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "Add Dockerfile for containerization

Multi-stage build with Python 3.10-slim base
Exposes MCP service ports and web dashboard
Uses entrypoint.sh for sequential startup"
```

---

## Task 3: Create entrypoint script

**Files:**
- Create: `entrypoint.sh`

**Step 1: Create entrypoint.sh with sequential startup logic**

Create `entrypoint.sh` in project root:

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
trap "echo '🛑 Stopping MCP services...'; kill $MCP_PID 2>/dev/null; exit 0" EXIT SIGTERM SIGINT
```

**Step 2: Make script executable**

Run: `chmod +x entrypoint.sh`
Expected: No output

**Step 3: Verify script has executable permissions**

Run: `ls -la entrypoint.sh | grep -E "^-rwxr"`
Expected: Shows executable permissions (x flags)

**Step 4: Commit**

```bash
git add entrypoint.sh
git commit -m "Add entrypoint script for container startup

Sequential execution: data fetch → MCP services → trading agent
Handles graceful shutdown of background services
Supports custom config file as argument"
```

---

## Task 4: Create docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

**Step 1: Create docker-compose.yml with service definition**

Create `docker-compose.yml` in project root:

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
      # AI Model API Configuration
      - OPENAI_API_BASE=${OPENAI_API_BASE}
      - OPENAI_API_KEY=${OPENAI_API_KEY}

      # Data Source Configuration
      - ALPHAADVANTAGE_API_KEY=${ALPHAADVANTAGE_API_KEY}
      - JINA_API_KEY=${JINA_API_KEY}

      # System Configuration
      - RUNTIME_ENV_PATH=/app/data/runtime_env.json

      # MCP Service Ports
      - MATH_HTTP_PORT=${MATH_HTTP_PORT:-8000}
      - SEARCH_HTTP_PORT=${SEARCH_HTTP_PORT:-8001}
      - TRADE_HTTP_PORT=${TRADE_HTTP_PORT:-8002}
      - GETPRICE_HTTP_PORT=${GETPRICE_HTTP_PORT:-8003}

      # Agent Configuration
      - AGENT_MAX_STEP=${AGENT_MAX_STEP:-30}
    ports:
      - "8000:8000"
      - "8001:8001"
      - "8002:8002"
      - "8003:8003"
      - "8888:8888"
    restart: unless-stopped
```

**Step 2: Validate YAML syntax**

Run: `docker-compose config 2>&1 | grep -i error || echo "YAML valid"`
Expected: "YAML valid" (or docker-compose shows parsed config)

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "Add docker-compose configuration

Mounts data and logs volumes for persistence
Injects environment variables from .env file
Exposes all MCP service ports and web dashboard
Auto-restart on failure"
```

---

## Task 5: Update .env.example for Docker

**Files:**
- Modify: `.env.example`

**Step 1: Read current .env.example**

Run: `cat .env.example`
Expected: Shows existing environment variable examples

**Step 2: Add Docker-specific documentation to .env.example**

Add these lines at the top of `.env.example` (or update existing variables):

```bash
# =============================================================================
# AI-Trader Environment Configuration
# =============================================================================
# Copy this file to .env and fill in your actual values
# Docker Compose automatically reads .env from project root

# AI Model API Configuration
OPENAI_API_BASE=https://your-openai-proxy.com/v1
OPENAI_API_KEY=your_openai_key_here

# Data Source Configuration
ALPHAADVANTAGE_API_KEY=your_alphavantage_key_here
JINA_API_KEY=your_jina_key_here

# System Configuration (Docker default paths)
RUNTIME_ENV_PATH=/app/data/runtime_env.json

# MCP Service Ports (defaults shown)
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003

# Agent Configuration
AGENT_MAX_STEP=30
```

**Step 3: Verify .env.example has all required variables**

Run: `grep -E "OPENAI_API_KEY|ALPHAADVANTAGE_API_KEY|JINA_API_KEY" .env.example`
Expected: Shows all three API key variables

**Step 4: Commit**

```bash
git add .env.example
git commit -m "Update .env.example with Docker configuration

Add Docker-specific paths and documentation
Include all required API keys and MCP ports
Show default values for optional settings"
```

---

## Task 6: Create Docker documentation

**Files:**
- Create: `docs/DOCKER.md`

**Step 1: Create docs/DOCKER.md with comprehensive usage guide**

Create `docs/DOCKER.md`:

```markdown
# Docker Deployment Guide

## Quick Start

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- API keys for OpenAI, Alpha Vantage, and Jina AI

### First-Time Setup

1. **Clone repository:**
   ```bash
   git clone https://github.com/HKUDS/AI-Trader.git
   cd AI-Trader
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

3. **Run with Docker Compose:**
   ```bash
   docker-compose up
   ```

That's it! The container will:
- Fetch latest price data from Alpha Vantage
- Start all MCP services
- Run the trading agent with default configuration

## Configuration

### Environment Variables

Edit `.env` file with your credentials:

```bash
# Required
OPENAI_API_KEY=sk-...
ALPHAADVANTAGE_API_KEY=...
JINA_API_KEY=...

# Optional (defaults shown)
MATH_HTTP_PORT=8000
SEARCH_HTTP_PORT=8001
TRADE_HTTP_PORT=8002
GETPRICE_HTTP_PORT=8003
AGENT_MAX_STEP=30
```

### Custom Trading Configuration

Pass a custom config file:

```bash
docker-compose run ai-trader configs/my_config.json
```

## Usage Examples

### Run in foreground with logs
```bash
docker-compose up
```

### Run in background (detached)
```bash
docker-compose up -d
docker-compose logs -f  # Follow logs
```

### Run with custom config
```bash
docker-compose run ai-trader configs/custom_config.json
```

### Stop containers
```bash
docker-compose down
```

### Rebuild after code changes
```bash
docker-compose build
docker-compose up
```

## Data Persistence

### Volume Mounts

Docker Compose mounts two volumes:

- `./data:/app/data` - Price data and trading records
- `./logs:/app/logs` - MCP service logs

Data persists across container restarts. To reset:

```bash
docker-compose down
rm -rf data/agent_data/* logs/*
docker-compose up
```

### Backup Trading Data

```bash
# Backup
tar -czf ai-trader-backup-$(date +%Y%m%d).tar.gz data/agent_data/

# Restore
tar -xzf ai-trader-backup-YYYYMMDD.tar.gz
```

## Using Pre-built Images

### Pull from GitHub Container Registry

```bash
docker pull ghcr.io/hkuds/ai-trader:latest
```

### Run without Docker Compose

```bash
docker run --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -p 8000-8003:8000-8003 \
  ghcr.io/hkuds/ai-trader:latest
```

### Specific version
```bash
docker pull ghcr.io/hkuds/ai-trader:v1.0.0
```

## Troubleshooting

### MCP Services Not Starting

**Symptom:** Container exits immediately or errors about ports

**Solutions:**
- Check ports 8000-8003 not already in use: `lsof -i :8000-8003`
- View container logs: `docker-compose logs`
- Check MCP service logs: `cat logs/math.log`

### Missing API Keys

**Symptom:** Errors about missing environment variables

**Solutions:**
- Verify `.env` file exists: `ls -la .env`
- Check required variables set: `grep OPENAI_API_KEY .env`
- Ensure `.env` in same directory as docker-compose.yml

### Data Fetch Failures

**Symptom:** Container exits during data preparation step

**Solutions:**
- Verify Alpha Vantage API key valid
- Check API rate limits (5 requests/minute for free tier)
- View logs: `docker-compose logs | grep "Fetching and merging"`

### Permission Issues

**Symptom:** Cannot write to data or logs directories

**Solutions:**
- Ensure directories writable: `chmod -R 755 data logs`
- Check volume mount permissions
- May need to create directories first: `mkdir -p data logs`

### Container Keeps Restarting

**Symptom:** Container restarts repeatedly

**Solutions:**
- View logs to identify error: `docker-compose logs --tail=50`
- Disable auto-restart: Comment out `restart: unless-stopped` in docker-compose.yml
- Check if main.py exits with error

## Advanced Usage

### Override Entrypoint

Run bash inside container for debugging:

```bash
docker-compose run --entrypoint /bin/bash ai-trader
```

### Build Multi-platform Images

For ARM64 (Apple Silicon) and AMD64:

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t ai-trader .
```

### View Container Resource Usage

```bash
docker stats ai-trader-app
```

### Access MCP Services Directly

Services exposed on host:
- Math: http://localhost:8000
- Search: http://localhost:8001
- Trade: http://localhost:8002
- Price: http://localhost:8003

## Development Workflow

### Local Code Changes

1. Edit code in project root
2. Rebuild image: `docker-compose build`
3. Run updated container: `docker-compose up`

### Test Different Configurations

```bash
# Create test config
cp configs/default_config.json configs/test_config.json
# Edit test_config.json

# Run with test config
docker-compose run ai-trader configs/test_config.json
```

## Production Deployment

For production use, consider:

1. **Use specific version tags** instead of `latest`
2. **External secrets management** (AWS Secrets Manager, etc.)
3. **Health checks** in docker-compose.yml
4. **Resource limits** (CPU/memory)
5. **Log aggregation** (ELK stack, CloudWatch)
6. **Orchestration** (Kubernetes, Docker Swarm)

See design document in `docs/plans/2025-10-30-docker-deployment-design.md` for architecture details.
```

**Step 2: Verify markdown formatting**

Run: `head -20 docs/DOCKER.md`
Expected: Shows properly formatted markdown header

**Step 3: Commit**

```bash
git add docs/DOCKER.md
git commit -m "Add Docker deployment documentation

Comprehensive guide including:
- Quick start instructions
- Configuration options
- Usage examples and volume persistence
- Troubleshooting common issues
- Pre-built image usage"
```

---

## Task 7: Update main README with Docker section

**Files:**
- Modify: `README.md`

**Step 1: Read current README to find insertion point**

Run: `grep -n "## 🚀 Quick Start" README.md`
Expected: Shows line number of Quick Start section

**Step 2: Add Docker section after Quick Start**

Insert this content after the "## 🚀 Quick Start" section (around line 210):

```markdown
## 🐳 Docker Deployment

### Using Docker Compose (Recommended)

The easiest way to run AI-Trader is with Docker Compose:

```bash
# 1. Clone and setup
git clone https://github.com/HKUDS/AI-Trader.git
cd AI-Trader

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys:
# - OPENAI_API_KEY
# - ALPHAADVANTAGE_API_KEY
# - JINA_API_KEY

# 3. Run with Docker Compose
docker-compose up
```

The container automatically:
- Fetches latest NASDAQ 100 price data
- Starts all MCP services
- Runs AI trading agents

### Using Pre-built Images

Pull and run pre-built images from GitHub Container Registry:

```bash
# Pull latest version
docker pull ghcr.io/hkuds/ai-trader:latest

# Run container
docker run --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  ghcr.io/hkuds/ai-trader:latest
```

**📖 See [docs/DOCKER.md](docs/DOCKER.md) for detailed Docker usage, troubleshooting, and advanced configuration.**

---
```

**Step 3: Verify Docker section added**

Run: `grep -A 5 "## 🐳 Docker Deployment" README.md`
Expected: Shows the Docker section content

**Step 4: Commit**

```bash
git add README.md
git commit -m "Add Docker deployment section to README

Include quick start with Docker Compose
Add pre-built image usage instructions
Link to detailed Docker documentation"
```

---

## Task 8: Create GitHub Actions workflow

**Files:**
- Create: `.github/workflows/docker-release.yml`

**Step 1: Create .github/workflows directory**

Run: `mkdir -p .github/workflows`
Expected: No output

**Step 2: Create docker-release.yml workflow**

Create `.github/workflows/docker-release.yml`:

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
          echo "Building version: $VERSION"

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

      - name: Image published
        run: |
          echo "✅ Docker image published successfully!"
          echo "📦 Pull with: docker pull ghcr.io/${{ github.repository_owner }}/ai-trader:${{ steps.meta.outputs.version }}"
          echo "📦 Or latest: docker pull ghcr.io/${{ github.repository_owner }}/ai-trader:latest"
```

**Step 3: Verify YAML syntax**

Run: `cat .github/workflows/docker-release.yml | grep -E "name:|on:|jobs:" | head -3`
Expected: Shows workflow name, triggers, and jobs

**Step 4: Commit**

```bash
git add .github/workflows/docker-release.yml
git commit -m "Add GitHub Actions workflow for Docker builds

Triggers on release tags (v*) and manual dispatch
Builds and pushes to GitHub Container Registry
Tags with both version and latest
Uses build caching for faster builds"
```

---

## Task 9: Update CLAUDE.md with Docker commands

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add Docker section to CLAUDE.md development commands**

Insert after the "### Starting Services" section in CLAUDE.md:

```markdown
### Docker Deployment

```bash
# Build Docker image
docker-compose build

# Run with Docker Compose
docker-compose up

# Run in background
docker-compose up -d

# Run with custom config
docker-compose run ai-trader configs/my_config.json

# View logs
docker-compose logs -f

# Stop and remove containers
docker-compose down

# Pull pre-built image
docker pull ghcr.io/hkuds/ai-trader:latest

# Test local Docker build
docker build -t ai-trader-test .
docker run --env-file .env -v $(pwd)/data:/app/data ai-trader-test
```

### Releasing Docker Images

```bash
# Create and push release tag
git tag v1.0.0
git push origin v1.0.0

# GitHub Actions automatically:
# 1. Builds Docker image
# 2. Tags with version and latest
# 3. Pushes to ghcr.io/hkuds/ai-trader

# Verify build in Actions tab
# https://github.com/HKUDS/AI-Trader/actions
```
```

**Step 2: Verify Docker commands added**

Run: `grep -A 10 "### Docker Deployment" CLAUDE.md`
Expected: Shows Docker commands section

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Update CLAUDE.md with Docker commands

Add Docker build and run commands
Include release process for Docker images
Document GitHub Actions automation"
```

---

## Task 10: Test Docker build locally

**Files:**
- None (verification task)

**Step 1: Build Docker image**

Run: `docker-compose build`
Expected: Build completes successfully, shows "Successfully built" and image ID

**Step 2: Verify image created**

Run: `docker images | grep ai-trader`
Expected: Shows ai-trader image with size and creation time

**Step 3: Test dry-run (without API keys)**

Create minimal test .env:
```bash
cat > .env.test << 'EOF'
OPENAI_API_KEY=test
ALPHAADVANTAGE_API_KEY=test
JINA_API_KEY=test
RUNTIME_ENV_PATH=/app/data/runtime_env.json
EOF
```

Run: `docker-compose --env-file .env.test config`
Expected: Shows parsed configuration without errors

**Step 4: Document test results**

Create file `docs/plans/docker-test-results.txt` with output from build

**Step 5: Commit test documentation**

```bash
git add docs/plans/docker-test-results.txt
git commit -m "Add Docker build test results

Local build verification completed successfully
Image builds without errors
Configuration parses correctly"
```

---

## Task 11: Create release checklist documentation

**Files:**
- Create: `docs/RELEASING.md`

**Step 1: Create release process documentation**

Create `docs/RELEASING.md`:

```markdown
# Release Process

## Creating a New Release

### 1. Prepare Release

1. Ensure `main` branch is stable and tests pass
2. Update version numbers if needed
3. Update CHANGELOG.md with release notes

### 2. Create Release Tag

```bash
# Ensure on main branch
git checkout main
git pull origin main

# Create annotated tag
git tag -a v1.0.0 -m "Release v1.0.0: Docker deployment support"

# Push tag to trigger CI/CD
git push origin v1.0.0
```

### 3. GitHub Actions Automation

Tag push automatically triggers `.github/workflows/docker-release.yml`:

1. ✅ Checks out code
2. ✅ Sets up Docker Buildx
3. ✅ Logs into GitHub Container Registry
4. ✅ Extracts version from tag
5. ✅ Builds Docker image with caching
6. ✅ Pushes to `ghcr.io/hkuds/ai-trader:VERSION`
7. ✅ Pushes to `ghcr.io/hkuds/ai-trader:latest`

### 4. Verify Build

1. Check GitHub Actions: https://github.com/HKUDS/AI-Trader/actions
2. Verify workflow completed successfully (green checkmark)
3. Check packages: https://github.com/HKUDS/AI-Trader/pkgs/container/ai-trader

### 5. Test Release

```bash
# Pull released image
docker pull ghcr.io/hkuds/ai-trader:v1.0.0

# Test run
docker run --env-file .env \
  -v $(pwd)/data:/app/data \
  ghcr.io/hkuds/ai-trader:v1.0.0
```

### 6. Create GitHub Release (Optional)

1. Go to https://github.com/HKUDS/AI-Trader/releases/new
2. Select tag: `v1.0.0`
3. Release title: `v1.0.0 - Docker Deployment Support`
4. Add release notes:

```markdown
## 🐳 Docker Deployment

This release adds full Docker support for easy deployment.

### Pull and Run

```bash
docker pull ghcr.io/hkuds/ai-trader:v1.0.0
docker run --env-file .env -v $(pwd)/data:/app/data ghcr.io/hkuds/ai-trader:v1.0.0
```

Or use Docker Compose:

```bash
docker-compose up
```

See [docs/DOCKER.md](docs/DOCKER.md) for details.

### What's New
- Docker containerization with single-container architecture
- docker-compose.yml for easy orchestration
- Automated CI/CD builds on release tags
- Pre-built images on GitHub Container Registry
```

5. Publish release

## Version Numbering

Use Semantic Versioning (SEMVER):

- `v1.0.0` - Major release (breaking changes)
- `v1.1.0` - Minor release (new features, backward compatible)
- `v1.1.1` - Patch release (bug fixes)

## Troubleshooting Releases

### Build Fails in GitHub Actions

1. Check Actions logs for error details
2. Test local build: `docker build .`
3. Fix issues and delete/recreate tag:

```bash
# Delete tag
git tag -d v1.0.0
git push origin :refs/tags/v1.0.0

# Recreate after fixes
git tag v1.0.0
git push origin v1.0.0
```

### Image Not Appearing in Registry

1. Check Actions permissions (Settings → Actions → General)
2. Verify `packages: write` permission in workflow
3. Ensure `GITHUB_TOKEN` has registry access

### Wrong Version Tagged

Delete and recreate:

```bash
git tag -d v1.0.0
git push origin :refs/tags/v1.0.0
git tag v1.0.1
git push origin v1.0.1
```

## Manual Build and Push

If automated build fails, manual push:

```bash
# Build locally
docker build -t ghcr.io/hkuds/ai-trader:v1.0.0 .

# Login to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Push
docker push ghcr.io/hkuds/ai-trader:v1.0.0
docker tag ghcr.io/hkuds/ai-trader:v1.0.0 ghcr.io/hkuds/ai-trader:latest
docker push ghcr.io/hkuds/ai-trader:latest
```
```

**Step 2: Verify release documentation complete**

Run: `grep -E "^## |^### " docs/RELEASING.md`
Expected: Shows all section headers

**Step 3: Commit**

```bash
git add docs/RELEASING.md
git commit -m "Add release process documentation

Complete guide for creating releases:
- Tag creation and push process
- GitHub Actions automation workflow
- Verification and testing steps
- Troubleshooting common issues"
```

---

## Task 12: Final validation and cleanup

**Files:**
- None (validation task)

**Step 1: Verify all Docker files created**

Run:
```bash
ls -la Dockerfile docker-compose.yml .dockerignore entrypoint.sh .github/workflows/docker-release.yml
```
Expected: All files exist with correct permissions

**Step 2: Verify documentation complete**

Run:
```bash
ls -la docs/DOCKER.md docs/RELEASING.md docs/plans/2025-10-30-docker-deployment-design.md
```
Expected: All documentation files exist

**Step 3: Verify git status clean**

Run: `git status`
Expected: Shows "working tree clean" or only untracked .env files

**Step 4: Review commit history**

Run: `git log --oneline -15`
Expected: Shows all 11+ commits from this implementation

**Step 5: Create summary commit if needed**

If any files uncommitted:
```bash
git add -A
git commit -m "Docker deployment implementation complete

All components implemented:
- Dockerfile with multi-stage build
- docker-compose.yml with volume mounts
- entrypoint.sh for sequential startup
- GitHub Actions workflow for releases
- Comprehensive documentation
- .dockerignore for clean builds"
```

---

## Testing Checklist

Before merging to main:

- [ ] Docker image builds successfully (`docker-compose build`)
- [ ] Image size reasonable (<500MB for base image)
- [ ] Container starts without errors (with test .env)
- [ ] MCP services start in container
- [ ] Volume mounts work (data/logs persist)
- [ ] Custom config file can be passed
- [ ] Documentation accurate and complete
- [ ] GitHub Actions workflow syntax valid
- [ ] .dockerignore excludes unnecessary files

## Post-Implementation

After merging:

1. Create test tag to verify GitHub Actions: `git tag v0.1.0-test`
2. Monitor Actions build
3. Test pulling from ghcr.io
4. Update project README.md if needed
5. Announce Docker support to users

---

**Implementation Complete!** All Docker deployment components created with comprehensive documentation and automated CI/CD.
