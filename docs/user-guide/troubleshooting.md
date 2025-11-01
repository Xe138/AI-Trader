# Troubleshooting Guide

Common issues and solutions for AI-Trader.

---

## Container Issues

### Container Won't Start

**Symptoms:**
- `docker ps` shows no ai-trader container
- Container exits immediately after starting

**Debug:**
```bash
# Check logs
docker logs ai-trader

# Check if container exists (stopped)
docker ps -a | grep ai-trader
```

**Common Causes & Solutions:**

**1. Missing API Keys**
```bash
# Verify .env file
cat .env | grep -E "OPENAI_API_KEY|ALPHAADVANTAGE_API_KEY|JINA_API_KEY"

# Should show all three keys with values
```

**Solution:** Add missing keys to `.env`

**2. Port Already in Use**
```bash
# Check what's using port 8080
sudo lsof -i :8080  # Linux/Mac
netstat -ano | findstr :8080  # Windows
```

**Solution:** Change port in `.env`:
```bash
echo "API_PORT=8889" >> .env
docker-compose down
docker-compose up -d
```

**3. Volume Permission Issues**
```bash
# Fix permissions
chmod -R 755 data logs configs
```

---

### Health Check Fails

**Symptoms:**
- `curl http://localhost:8080/health` returns error or HTML page
- Container running but API not responding

**Debug:**
```bash
# Check if API process is running
docker exec ai-trader ps aux | grep uvicorn

# Test internal health (always port 8080 inside container)
docker exec ai-trader curl http://localhost:8080/health

# Check configured port
grep API_PORT .env
```

**Solutions:**

**If you get HTML 404 page:**
Another service is using your configured port.

```bash
# Find conflicting service
sudo lsof -i :8080

# Change AI-Trader port
echo "API_PORT=8889" >> .env
docker-compose down
docker-compose up -d

# Now use new port
curl http://localhost:8889/health
```

**If MCP services didn't start:**
```bash
# Check MCP processes
docker exec ai-trader ps aux | grep python

# Should see 4 MCP services on ports 8000-8003
```

**If database issues:**
```bash
# Check database file
docker exec ai-trader ls -l /app/data/jobs.db

# If missing, restart to recreate
docker-compose restart
```

---

## Simulation Issues

### Job Stays in "Pending" Status

**Symptoms:**
- Job triggered but never progresses to "running"
- Status remains "pending" indefinitely

**Debug:**
```bash
# Check worker logs
docker logs ai-trader | grep -i "worker\|simulation"

# Check database
docker exec ai-trader sqlite3 /app/data/jobs.db "SELECT * FROM job_details;"

# Check MCP service accessibility
docker exec ai-trader curl http://localhost:8000/health
```

**Solutions:**

```bash
# Restart container (jobs resume automatically)
docker-compose restart

# Check specific job status with details
curl http://localhost:8080/simulate/status/$JOB_ID | jq '.details'
```

---

### Job Takes Too Long / Timeouts

**Symptoms:**
- Jobs taking longer than expected
- Test scripts timing out

**Expected Execution Times:**
- Single model-day: 2-5 minutes (with cached price data)
- First run with data download: 10-15 minutes
- 2-date, 2-model job: 10-20 minutes

**Solutions:**

**Increase poll timeout in monitoring:**
```bash
# Instead of fixed polling, use this
while true; do
  STATUS=$(curl -s http://localhost:8080/simulate/status/$JOB_ID | jq -r '.status')
  echo "$(date): Status = $STATUS"
  
  if [[ "$STATUS" == "completed" ]] || [[ "$STATUS" == "partial" ]] || [[ "$STATUS" == "failed" ]]; then
    break
  fi
  
  sleep 30
done
```

**Check if agent is stuck:**
```bash
# View real-time logs
docker logs -f ai-trader

# Look for repeated errors or infinite loops
```

---

### "No trading dates with complete price data"

**Error Message:**
```
No trading dates with complete price data in range 2025-01-16 to 2025-01-17. 
All symbols must have data for a date to be tradeable.
```

**Cause:** Missing price data for requested dates.

**Solutions:**

**Option 1: Try Recent Dates**

Use more recent dates where data is more likely available:
```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{"start_date": "2024-12-15", "models": ["gpt-4"]}'
```

**Option 2: Manually Download Data**

```bash
docker exec -it ai-trader bash
cd data
python get_daily_price.py  # Downloads latest data
python merge_jsonl.py       # Merges into database
exit

# Retry simulation
```

**Option 3: Check Auto-Download Setting**

```bash
# Ensure auto-download is enabled
grep AUTO_DOWNLOAD_PRICE_DATA .env

# Should be: AUTO_DOWNLOAD_PRICE_DATA=true
```

---

### Rate Limit Errors

**Symptoms:**
- Logs show "rate limit" messages
- Partial data downloaded

**Cause:** Alpha Vantage API rate limits (5 req/min free tier, 75 req/min premium)

**Solutions:**

**For free tier:**
- Simulations automatically continue with available data
- Next simulation resumes downloads
- Consider upgrading to premium API key

**Workaround:**
```bash
# Pre-download data in batches
docker exec -it ai-trader bash
cd data

# Download in stages (wait 1 min between runs)
python get_daily_price.py
sleep 60
python get_daily_price.py
sleep 60
python get_daily_price.py

python merge_jsonl.py
exit
```

---

## API Issues

### 400 Bad Request: Another Job Running

**Error:**
```json
{
  "detail": "Another simulation job is already running or pending. Please wait for it to complete."
}
```

**Cause:** AI-Trader allows only 1 concurrent job by default.

**Solutions:**

**Check current jobs:**
```bash
# Find running job
curl http://localhost:8080/health  # Verify API is up

# Query recent jobs (need to check database)
docker exec ai-trader sqlite3 /app/data/jobs.db \
  "SELECT job_id, status FROM jobs ORDER BY created_at DESC LIMIT 5;"
```

**Wait for completion:**
```bash
# Get the blocking job's status
curl http://localhost:8080/simulate/status/{job_id}
```

**Force-stop stuck job (last resort):**
```bash
# Update job status in database
docker exec ai-trader sqlite3 /app/data/jobs.db \
  "UPDATE jobs SET status='failed' WHERE status IN ('pending', 'running');"

# Restart service
docker-compose restart
```

---

### Invalid Date Format Errors

**Error:**
```json
{
  "detail": "Invalid date format: 2025-1-16. Expected YYYY-MM-DD"
}
```

**Solution:** Use zero-padded dates:

```bash
# Wrong
{"start_date": "2025-1-16"}

# Correct
{"start_date": "2025-01-16"}
```

---

### Date Range Too Large

**Error:**
```json
{
  "detail": "Date range too large: 45 days. Maximum allowed: 30 days"
}
```

**Solution:** Split into smaller batches:

```bash
# Instead of 2025-01-01 to 2025-02-15 (45 days)
# Run as two jobs:

# Job 1: Jan 1-30
curl -X POST http://localhost:8080/simulate/trigger \
  -d '{"start_date": "2025-01-01", "end_date": "2025-01-30"}'

# Job 2: Jan 31 - Feb 15
curl -X POST http://localhost:8080/simulate/trigger \
  -d '{"start_date": "2025-01-31", "end_date": "2025-02-15"}'
```

---

## Data Issues

### Database Corruption

**Symptoms:**
- "database disk image is malformed"
- Unexpected SQL errors

**Solutions:**

**Backup and rebuild:**
```bash
# Stop service
docker-compose down

# Backup current database
cp data/jobs.db data/jobs.db.backup

# Try recovery
docker run --rm -v $(pwd)/data:/data alpine sqlite3 /data/jobs.db "PRAGMA integrity_check;"

# If corrupted, delete and restart (loses job history)
rm data/jobs.db
docker-compose up -d
```

---

### Missing Price Data Files

**Symptoms:**
- Errors about missing `merged.jsonl`
- Price query failures

**Solution:**

```bash
# Re-download price data
docker exec -it ai-trader bash
cd data
python get_daily_price.py
python merge_jsonl.py
ls -lh merged.jsonl  # Should exist
exit
```

---

## Performance Issues

### Slow Simulation Execution

**Typical speeds:**
- Single model-day: 2-5 minutes
- With cold start (first time): +3-5 minutes

**Causes & Solutions:**

**1. AI Model API is slow**
- Check AI provider status page
- Try different model
- Increase timeout in config

**2. Network latency**
- Check internet connection
- Jina Search API might be slow

**3. MCP services overloaded**
```bash
# Check CPU usage
docker stats ai-trader
```

---

### High Memory Usage

**Normal:** 500MB - 1GB during simulation

**If higher:**
```bash
# Check memory
docker stats ai-trader

# Restart if needed
docker-compose restart
```

---

## Diagnostic Commands

```bash
# Container status
docker ps | grep ai-trader

# Real-time logs
docker logs -f ai-trader

# Check errors only
docker logs ai-trader 2>&1 | grep -i error

# Container resource usage
docker stats ai-trader

# Access container shell
docker exec -it ai-trader bash

# Database inspection
docker exec -it ai-trader sqlite3 /app/data/jobs.db
sqlite> SELECT * FROM jobs ORDER BY created_at DESC LIMIT 5;
sqlite> SELECT status, COUNT(*) FROM jobs GROUP BY status;
sqlite> .quit

# Check file permissions
docker exec ai-trader ls -la /app/data

# Test API connectivity
curl -v http://localhost:8080/health

# View all environment variables
docker exec ai-trader env | sort
```

---

## Getting More Help

If your issue isn't covered here:

1. **Check logs** for specific error messages
2. **Review** [API_REFERENCE.md](../../API_REFERENCE.md) for correct usage
3. **Search** [GitHub Issues](https://github.com/Xe138/AI-Trader/issues)
4. **Open new issue** with:
   - Error messages from logs
   - Steps to reproduce
   - Environment details (OS, Docker version)
   - Relevant config files (redact API keys)
