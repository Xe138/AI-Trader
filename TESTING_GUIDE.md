# AI-Trader Testing & Validation Guide

This guide provides step-by-step instructions for validating the AI-Trader Docker deployment.

## Prerequisites

- Docker Desktop installed and running
- `.env` file configured with API keys
- At least 2GB free disk space
- Internet connection for initial price data download

## Quick Start

```bash
# 1. Make scripts executable
chmod +x scripts/*.sh

# 2. Validate Docker build
bash scripts/validate_docker_build.sh

# 3. Test API endpoints
bash scripts/test_api_endpoints.sh
```

---

## Detailed Testing Procedures

### Test 1: Docker Build Validation

**Purpose:** Verify Docker image builds correctly and containers start

**Command:**
```bash
bash scripts/validate_docker_build.sh
```

**What it tests:**
- ✅ Docker and docker-compose installed
- ✅ Docker daemon running
- ✅ `.env` file exists and configured
- ✅ Image builds successfully
- ✅ Container starts in API mode
- ✅ Health endpoint responds
- ✅ No critical errors in logs

**Expected output:**
```
==========================================
AI-Trader Docker Build Validation
==========================================

Step 1: Checking prerequisites...
✓ Docker is installed: Docker version 24.0.0
✓ Docker daemon is running
✓ docker-compose is installed

Step 2: Checking environment configuration...
✓ .env file exists
✓ OPENAI_API_KEY is set
✓ ALPHAADVANTAGE_API_KEY is set
✓ JINA_API_KEY is set

Step 3: Building Docker image...
✓ Docker image built successfully

Step 4: Verifying Docker image...
✓ Image size: 850MB
✓ Exposed ports: 8000/tcp 8001/tcp 8002/tcp 8003/tcp 8080/tcp 8888/tcp

Step 5: Testing API mode startup...
✓ Container started successfully
✓ Container is running
✓ No critical errors in logs

Step 6: Testing health endpoint...
✓ Health endpoint responding
Health response: {"status":"healthy","database":"connected","timestamp":"..."}
```

**If it fails:**
- Check Docker Desktop is running
- Verify `.env` has all required keys
- Check port 8080 is not already in use
- Review logs: `docker logs ai-trader`

---

### Test 2: API Endpoint Testing

**Purpose:** Validate all REST API endpoints work correctly

**Command:**
```bash
# Ensure API is running first
docker-compose up -d ai-trader

# Run tests
bash scripts/test_api_endpoints.sh
```

**What it tests:**
- ✅ GET /health - Service health check
- ✅ POST /simulate/trigger - Job creation
- ✅ GET /simulate/status/{job_id} - Status tracking
- ✅ Job completion monitoring
- ✅ GET /results - Results retrieval
- ✅ Query filtering (by date, model)
- ✅ Concurrent job prevention
- ✅ Error handling (invalid inputs)

**Expected output:**
```
==========================================
AI-Trader API Endpoint Testing
==========================================

✓ API is accessible

Test 1: GET /health
✓ Health check passed

Test 2: POST /simulate/trigger
✓ Simulation triggered successfully
Job ID: 550e8400-e29b-41d4-a716-446655440000

Test 3: GET /simulate/status/{job_id}
✓ Job status retrieved
Job Status: pending

Test 4: Monitoring job progress
[1/30] Status: running | Progress: {"completed":1,"failed":0,...}
...
✓ Job finished with status: completed

Test 5: GET /results
✓ Results retrieved
Result count: 2

Test 6: GET /results?date=...
✓ Date-filtered results retrieved

Test 7: GET /results?model=...
✓ Model-filtered results retrieved

Test 8: Concurrent job prevention
✓ Concurrent job correctly rejected

Test 9: Error handling
✓ Invalid config path correctly rejected
```

**If it fails:**
- Ensure container is running: `docker ps | grep ai-trader`
- Check API logs: `docker logs ai-trader`
- Verify port 8080 is accessible: `curl http://localhost:8080/health`
- Check MCP services started: `docker exec ai-trader ps aux | grep python`

---


## Manual Testing Procedures

### Test 1: API Health Check

```bash
# Start API
docker-compose up -d ai-trader

# Test health endpoint
curl http://localhost:8080/health

# Expected response:
# {"status":"healthy","database":"connected","timestamp":"2025-01-16T10:00:00Z"}
```

### Test 2: Trigger Simulation

```bash
# Trigger job
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "config_path": "/app/configs/default_config.json",
    "date_range": ["2025-01-16", "2025-01-17"],
    "models": ["gpt-4"]
  }'

# Expected response:
# {
#   "job_id": "550e8400-e29b-41d4-a716-446655440000",
#   "status": "pending",
#   "total_model_days": 2,
#   "message": "Simulation job ... created and started"
# }

# Save job_id for next steps
JOB_ID="550e8400-e29b-41d4-a716-446655440000"
```

### Test 3: Monitor Job Progress

```bash
# Check status (repeat until completed)
curl http://localhost:8080/simulate/status/$JOB_ID | jq '.'

# Poll with watch
watch -n 10 "curl -s http://localhost:8080/simulate/status/$JOB_ID | jq '.status, .progress'"
```

### Test 4: Retrieve Results

```bash
# Get all results for job
curl "http://localhost:8080/results?job_id=$JOB_ID" | jq '.'

# Filter by date
curl "http://localhost:8080/results?date=2025-01-16" | jq '.'

# Filter by model
curl "http://localhost:8080/results?model=gpt-4" | jq '.'

# Combine filters
curl "http://localhost:8080/results?job_id=$JOB_ID&date=2025-01-16&model=gpt-4" | jq '.'
```

### Test 5: Volume Persistence

```bash
# Stop container
docker-compose down

# Verify data persists
ls -lh data/jobs.db
ls -R data/agent_data

# Restart container
docker-compose up -d ai-trader

# Data should still be accessible via API
curl http://localhost:8080/results | jq '.count'
```

---

## Troubleshooting

### Problem: Container won't start

**Symptoms:**
- `docker ps` shows no ai-trader container
- Container exits immediately

**Debug steps:**
```bash
# Check logs
docker logs ai-trader

# Common issues:
# 1. Missing API keys in .env
# 2. Port 8080 already in use
# 3. Volume permission issues
```

**Solutions:**
```bash
# 1. Verify .env
cat .env | grep -E "OPENAI_API_KEY|ALPHAADVANTAGE_API_KEY|JINA_API_KEY"

# 2. Check port usage
lsof -i :8080  # Linux/Mac
netstat -ano | findstr :8080  # Windows

# 3. Fix permissions
chmod -R 755 data logs
```

### Problem: Health check fails

**Symptoms:**
- `curl http://localhost:8080/health` returns error
- Container is running but API not responding

**Debug steps:**
```bash
# Check if API process is running
docker exec ai-trader ps aux | grep uvicorn

# Check internal health
docker exec ai-trader curl http://localhost:8080/health

# Check logs for startup errors
docker logs ai-trader | grep -i error
```

**Solutions:**
```bash
# If MCP services didn't start:
docker exec ai-trader ps aux | grep python

# If database issues:
docker exec ai-trader ls -l /app/data/jobs.db

# Restart container
docker-compose restart ai-trader
```

### Problem: Job stays in "pending" status

**Symptoms:**
- Job triggered but never progresses
- Status remains "pending" indefinitely

**Debug steps:**
```bash
# Check worker logs
docker logs ai-trader | grep -i "worker\|simulation"

# Check database
docker exec ai-trader sqlite3 /app/data/jobs.db "SELECT * FROM job_details;"

# Check if MCP services are accessible
docker exec ai-trader curl http://localhost:8000/health
```

**Solutions:**
```bash
# Restart container (jobs resume automatically)
docker-compose restart ai-trader

# Check specific job status
curl http://localhost:8080/simulate/status/$JOB_ID | jq '.details'
```

### Problem: Tests timeout

**Symptoms:**
- `test_api_endpoints.sh` hangs during job monitoring
- Jobs take longer than expected

**Solutions:**
```bash
# Increase poll timeout in test script
# Edit: MAX_POLLS=60  # Increase from 30

# Or monitor job manually
watch -n 30 "curl -s http://localhost:8080/simulate/status/$JOB_ID | jq '.status, .progress'"

# Check agent logs for slowness
docker logs ai-trader | tail -100
```

---

## Performance Benchmarks

### Expected Execution Times

**Docker Build:**
- First build: 5-10 minutes
- Subsequent builds: 1-2 minutes (with cache)

**API Startup:**
- Container start: 5-10 seconds
- Health check ready: 15-20 seconds (including MCP services)

**Single Model-Day Simulation:**
- With existing price data: 2-5 minutes
- First run (fetching price data): 10-15 minutes

**Complete 2-Date, 2-Model Job:**
- Expected duration: 10-20 minutes
- Depends on AI model response times

---

## Continuous Monitoring

### Health Check Monitoring

```bash
# Add to cron for continuous monitoring
*/5 * * * * curl -f http://localhost:8080/health || echo "API down" | mail -s "AI-Trader Alert" admin@example.com
```

### Log Rotation

```bash
# Docker handles log rotation, but monitor size:
docker logs ai-trader --tail 100

# Clear old logs if needed:
docker logs ai-trader > /dev/null 2>&1
```

### Database Size

```bash
# Monitor database growth
docker exec ai-trader du -h /app/data/jobs.db

# Vacuum periodically
docker exec ai-trader sqlite3 /app/data/jobs.db "VACUUM;"
```

---

## Success Criteria

### Validation Complete When:

- ✅ Both test scripts pass without errors
- ✅ Health endpoint returns "healthy" status
- ✅ Can trigger and complete simulation job
- ✅ Results are retrievable via API
- ✅ Data persists after container restart
- ✅ No critical errors in logs

### Ready for Production When:

- ✅ All validation tests pass
- ✅ Performance meets expectations
- ✅ Monitoring is configured
- ✅ Backup strategy is in place
- ✅ Documentation is reviewed
- ✅ Team is trained on operations

---

## Next Steps After Validation

1. **Set up monitoring** - Configure health check alerts
2. **Configure backups** - Backup `/app/data` regularly
3. **Document operations** - Create runbook for team
4. **Set up CI/CD** - Automate testing and deployment
5. **Integrate with Windmill** - Connect workflows to API
6. **Scale if needed** - Deploy multiple instances with load balancer

---

## Support

For issues not covered in this guide:

1. Check `DOCKER_API.md` for detailed API documentation
2. Review container logs: `docker logs ai-trader`
3. Check database: `docker exec ai-trader sqlite3 /app/data/jobs.db ".tables"`
4. Open issue on GitHub with logs and error messages
