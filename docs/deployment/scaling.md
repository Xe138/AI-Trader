# Scaling

Running multiple instances and load balancing.

---

## Current Limitations

- Maximum 1 concurrent job per instance
- No built-in load balancing
- Single SQLite database per instance

---

## Multi-Instance Deployment

For parallel simulations, deploy multiple instances:

```yaml
# docker-compose.yml
services:
  ai-trader-server-1:
    image: ghcr.io/xe138/ai-trader-server:latest
    ports:
      - "8081:8080"
    volumes:
      - ./data1:/app/data

  ai-trader-server-2:
    image: ghcr.io/xe138/ai-trader-server:latest
    ports:
      - "8082:8080"
    volumes:
      - ./data2:/app/data
```

**Note:** Each instance needs separate database and data volumes.

---

## Load Balancing (Future)

Planned for v0.4.0:
- Shared PostgreSQL database
- Job queue with multiple workers
- Horizontal scaling support
