# Using the API

Common workflows and best practices for AI-Trader API.

---

## Basic Workflow

### 1. Trigger Simulation

```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2025-01-16",
    "end_date": "2025-01-17",
    "models": ["gpt-4"]
  }'
```

Save the `job_id` from response.

### 2. Poll for Completion

```bash
JOB_ID="your-job-id-here"

while true; do
  STATUS=$(curl -s http://localhost:8080/simulate/status/$JOB_ID | jq -r '.status')
  echo "Status: $STATUS"
  
  if [[ "$STATUS" == "completed" ]] || [[ "$STATUS" == "partial" ]] || [[ "$STATUS" == "failed" ]]; then
    break
  fi
  
  sleep 10
done
```

### 3. Retrieve Results

```bash
curl "http://localhost:8080/results?job_id=$JOB_ID" | jq '.'
```

---

## Common Patterns

### Single-Day Simulation

Omit `end_date` to simulate just one day:

```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -d '{"start_date": "2025-01-16", "models": ["gpt-4"]}'
```

### All Enabled Models

Omit `models` to run all enabled models from config:

```bash
curl -X POST http://localhost:8080/simulate/trigger \
  -d '{"start_date": "2025-01-16", "end_date": "2025-01-20"}'
```

### Filter Results

```bash
# By date
curl "http://localhost:8080/results?date=2025-01-16"

# By model
curl "http://localhost:8080/results?model=gpt-4"

# Combined
curl "http://localhost:8080/results?job_id=$JOB_ID&date=2025-01-16&model=gpt-4"
```

---

## Best Practices

### 1. Check Health Before Triggering

```bash
curl http://localhost:8080/health

# Only proceed if status is "healthy"
```

### 2. Use Exponential Backoff for Retries

```python
import time
import requests

def trigger_with_retry(max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "http://localhost:8080/simulate/trigger",
                json={"start_date": "2025-01-16"}
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            if e.response.status_code == 400:
                # Don't retry on validation errors
                raise
            wait = 2 ** attempt  # 1s, 2s, 4s
            time.sleep(wait)
    
    raise Exception("Max retries exceeded")
```

### 3. Handle Concurrent Job Conflicts

```python
response = requests.post(
    "http://localhost:8080/simulate/trigger",
    json={"start_date": "2025-01-16"}
)

if response.status_code == 400 and "already running" in response.json()["detail"]:
    print("Another job is running. Waiting...")
    # Wait and retry, or query existing job status
```

### 4. Monitor Progress with Details

```python
def get_detailed_progress(job_id):
    response = requests.get(f"http://localhost:8080/simulate/status/{job_id}")
    status = response.json()
    
    print(f"Overall: {status['status']}")
    print(f"Progress: {status['progress']['completed']}/{status['progress']['total_model_days']}")
    
    # Show per-model-day status
    for detail in status['details']:
        print(f"  {detail['trading_date']} {detail['model_signature']}: {detail['status']}")
```

---

## Error Handling

### Validation Errors (400)

```python
try:
    response = requests.post(
        "http://localhost:8080/simulate/trigger",
        json={"start_date": "2025-1-16"}  # Wrong format
    )
    response.raise_for_status()
except requests.HTTPError as e:
    if e.response.status_code == 400:
        print(f"Validation error: {e.response.json()['detail']}")
        # Fix input and retry
```

### Service Unavailable (503)

```python
try:
    response = requests.post(
        "http://localhost:8080/simulate/trigger",
        json={"start_date": "2025-01-16"}
    )
    response.raise_for_status()
except requests.HTTPError as e:
    if e.response.status_code == 503:
        print("Service unavailable (likely price data download failed)")
        # Retry later or check ALPHAADVANTAGE_API_KEY
```

---

See [API_REFERENCE.md](../../API_REFERENCE.md) for complete endpoint documentation.
