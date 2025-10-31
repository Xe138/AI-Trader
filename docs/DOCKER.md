# Docker Deployment Guide

## Quick Start

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- API keys for OpenAI, Alpha Vantage, and Jina AI

### First-Time Setup

1. **Clone repository:**
   ```bash
   git clone https://github.com/Xe138/AI-Trader.git
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

**Simple Method (Recommended):**

Create a `configs/custom_config.json` file - it will be automatically used:

```bash
# Copy default config as starting point
cp configs/default_config.json configs/custom_config.json

# Edit your custom config
nano configs/custom_config.json

# Run normally - custom_config.json is automatically detected!
docker-compose up
```

**Priority order:**
1. `configs/custom_config.json` (if exists) - **Highest priority**
2. Command-line argument: `docker-compose run ai-trader configs/other.json`
3. `configs/default_config.json` (fallback)

**Advanced: Use a different config file name:**

```bash
docker-compose run ai-trader configs/my_special_config.json
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

Docker Compose mounts three volumes:

- `./data:/app/data` - Price data and trading records
- `./logs:/app/logs` - MCP service logs
- `./configs:/app/configs` - Configuration files (allows editing configs without rebuilding)

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

**Method 1: Use the standard custom_config.json**

```bash
# Create and edit your config
cp configs/default_config.json configs/custom_config.json
nano configs/custom_config.json

# Run - automatically uses custom_config.json
docker-compose up
```

**Method 2: Test multiple configs with different names**

```bash
# Create multiple test configs
cp configs/default_config.json configs/conservative.json
cp configs/default_config.json configs/aggressive.json

# Edit each config...

# Test conservative strategy
docker-compose run ai-trader configs/conservative.json

# Test aggressive strategy
docker-compose run ai-trader configs/aggressive.json
```

**Method 3: Temporarily switch configs**

```bash
# Temporarily rename your custom config
mv configs/custom_config.json configs/custom_config.json.backup
cp configs/test_strategy.json configs/custom_config.json

# Run with test strategy
docker-compose up

# Restore original
mv configs/custom_config.json.backup configs/custom_config.json
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
