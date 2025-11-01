# Testing Guide

Guide for testing AI-Trader during development.

---

## Automated Testing

### Docker Build Validation

```bash
chmod +x scripts/*.sh
bash scripts/validate_docker_build.sh
```

Validates:
- Docker installation
- Environment configuration
- Image build
- Container startup
- Health endpoint

### API Endpoint Testing

```bash
bash scripts/test_api_endpoints.sh
```

Tests all API endpoints with real simulations.

---

## Unit Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=api --cov-report=term-missing

# Specific test file
pytest tests/unit/test_job_manager.py -v
```

---

##  Integration Tests

```bash
# Run integration tests only
pytest tests/integration/ -v

# Test with real API server
docker-compose up -d
pytest tests/integration/test_api_endpoints.py -v
```

---

For detailed testing procedures, see root [TESTING_GUIDE.md](../../TESTING_GUIDE.md).
