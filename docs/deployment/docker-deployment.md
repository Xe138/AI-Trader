# Docker Deployment

Production Docker deployment guide.

---

## Quick Deployment

```bash
git clone https://github.com/Xe138/AI-Trader.git
cd AI-Trader
cp .env.example .env
# Edit .env with API keys
docker-compose up -d
```

---

## Production Configuration

### Use Pre-built Image

```yaml
# docker-compose.yml
services:
  ai-trader:
    image: ghcr.io/xe138/ai-trader:latest
    # ... rest of config
```

### Build Locally

```yaml
# docker-compose.yml
services:
  ai-trader:
    build: .
    # ... rest of config
```

---

## Volume Persistence

Ensure data persists across restarts:

```yaml
volumes:
  - ./data:/app/data          # Required: database and cache
  - ./logs:/app/logs          # Recommended: application logs
  - ./configs:/app/configs    # Required: model configurations
```

---

## Environment Security

- Never commit `.env` to version control
- Use secrets management (Docker secrets, Kubernetes secrets)
- Rotate API keys regularly
- Restrict network access to API port

---

## Health Checks

Docker automatically restarts unhealthy containers:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

---

## Monitoring

```bash
# Container status
docker ps

# Resource usage
docker stats ai-trader

# Logs
docker logs -f ai-trader
```

---

See [DOCKER_API.md](../../DOCKER_API.md) for detailed Docker documentation.
