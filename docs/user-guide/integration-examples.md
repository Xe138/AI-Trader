# Integration Examples

Examples for integrating AI-Trader-Server with external systems.

---

## Python

See complete Python client in [API_REFERENCE.md](../../API_REFERENCE.md#client-libraries).

### Async Client

```python
import aiohttp
import asyncio

class AsyncAITraderServerClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url

    async def trigger_simulation(self, start_date, end_date=None, models=None):
        payload = {"start_date": start_date}
        if end_date:
            payload["end_date"] = end_date
        if models:
            payload["models"] = models

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/simulate/trigger",
                json=payload
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def wait_for_completion(self, job_id, poll_interval=10):
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(
                    f"{self.base_url}/simulate/status/{job_id}"
                ) as response:
                    status = await response.json()

                    if status["status"] in ["completed", "partial", "failed"]:
                        return status

                    await asyncio.sleep(poll_interval)

# Usage
async def main():
    client = AsyncAITraderServerClient()
    job = await client.trigger_simulation("2025-01-16", models=["gpt-4"])
    result = await client.wait_for_completion(job["job_id"])
    print(f"Simulation completed: {result['status']}")

asyncio.run(main())
```

---

## TypeScript/JavaScript

See complete TypeScript client in [API_REFERENCE.md](../../API_REFERENCE.md#client-libraries).

---

## Bash/Shell Scripts

### Daily Automation

```bash
#!/bin/bash
# daily_simulation.sh

API_URL="http://localhost:8080"
DATE=$(date -d "yesterday" +%Y-%m-%d)

echo "Triggering simulation for $DATE"

# Trigger
RESPONSE=$(curl -s -X POST $API_URL/simulate/trigger \
  -H "Content-Type: application/json" \
  -d "{\"start_date\": \"$DATE\", \"models\": [\"gpt-4\"]}")

JOB_ID=$(echo $RESPONSE | jq -r '.job_id')
echo "Job ID: $JOB_ID"

# Poll
while true; do
  STATUS=$(curl -s $API_URL/simulate/status/$JOB_ID | jq -r '.status')
  echo "Status: $STATUS"

  if [[ "$STATUS" == "completed" ]] || [[ "$STATUS" == "partial" ]] || [[ "$STATUS" == "failed" ]]; then
    break
  fi

  sleep 30
done

# Get results
curl -s "$API_URL/results?job_id=$JOB_ID" | jq '.' > results_$DATE.json
echo "Results saved to results_$DATE.json"
```

Add to crontab:
```bash
0 6 * * * /path/to/daily_simulation.sh >> /var/log/ai-trader-server.log 2>&1
```

---

## Apache Airflow

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import requests
import time

def trigger_simulation(**context):
    response = requests.post(
        "http://ai-trader-server:8080/simulate/trigger",
        json={"start_date": "{{ ds }}", "models": ["gpt-4"]}
    )
    response.raise_for_status()
    return response.json()["job_id"]

def wait_for_completion(**context):
    job_id = context["task_instance"].xcom_pull(task_ids="trigger")

    while True:
        response = requests.get(f"http://ai-trader-server:8080/simulate/status/{job_id}")
        status = response.json()

        if status["status"] in ["completed", "partial", "failed"]:
            return status

        time.sleep(30)

def fetch_results(**context):
    job_id = context["task_instance"].xcom_pull(task_ids="trigger")
    response = requests.get(f"http://ai-trader-server:8080/results?job_id={job_id}")
    return response.json()

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "ai_trader_server_simulation",
    default_args=default_args,
    schedule_interval="0 6 * * *",  # Daily at 6 AM
    catchup=False
)

trigger_task = PythonOperator(
    task_id="trigger",
    python_callable=trigger_simulation,
    dag=dag
)

wait_task = PythonOperator(
    task_id="wait",
    python_callable=wait_for_completion,
    dag=dag
)

fetch_task = PythonOperator(
    task_id="fetch_results",
    python_callable=fetch_results,
    dag=dag
)

trigger_task >> wait_task >> fetch_task
```

---

## Generic Workflow Automation

Any HTTP-capable automation service can integrate with AI-Trader-Server:

1. **Trigger:** POST to `/simulate/trigger`
2. **Poll:** GET `/simulate/status/{job_id}` every 10-30 seconds
3. **Retrieve:** GET `/results?job_id={job_id}` when complete
4. **Store:** Save results to your database/warehouse

**Key considerations:**
- Handle 400 errors (concurrent jobs) gracefully
- Implement exponential backoff for retries
- Monitor health endpoint before triggering
- Store job_id for tracking and debugging
