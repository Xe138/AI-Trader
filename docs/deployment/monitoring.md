# Monitoring

Health checks, logging, and metrics.

---

## Health Checks

```bash
# Manual check
curl http://localhost:8080/health

# Automated monitoring (cron)
*/5 * * * * curl -f http://localhost:8080/health || echo "API down" | mail -s "Alert" admin@example.com
```

---

## Logging

```bash
# View logs
docker logs -f ai-trader-server

# Filter errors
docker logs ai-trader-server 2>&1 | grep -i error

# Export logs
docker logs ai-trader-server > ai-trader-server.log 2>&1
```

---

## Database Monitoring

```bash
# Database size
docker exec ai-trader-server du -h /app/data/jobs.db

# Job statistics
docker exec ai-trader-server sqlite3 /app/data/jobs.db \
  "SELECT status, COUNT(*) FROM jobs GROUP BY status;"
```

---

## Metrics (Future)

Prometheus metrics planned for v0.4.0.
