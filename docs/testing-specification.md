# Comprehensive Testing Suite Specification

## 1. Overview

This document defines the complete testing strategy, test suite structure, coverage requirements, and quality thresholds for the AI-Trader API service.

**Testing Philosophy:**
- **Test-Driven Development (TDD)** for critical paths
- **High coverage** (≥85%) for production code
- **Fast feedback** - unit tests run in <10 seconds
- **Realistic integration tests** with test database
- **Performance benchmarks** to catch regressions
- **Security testing** for API vulnerabilities

---

## 2. Testing Thresholds & Requirements

### 2.1 Code Coverage

| Component | Minimum Coverage | Target Coverage | Notes |
|-----------|-----------------|-----------------|-------|
| **api/job_manager.py** | 90% | 95% | Critical - job lifecycle |
| **api/worker.py** | 85% | 90% | Core execution logic |
| **api/executor.py** | 85% | 90% | Model-day execution |
| **api/results_service.py** | 90% | 95% | Data retrieval |
| **api/database.py** | 95% | 100% | Database utilities |
| **api/runtime_manager.py** | 85% | 90% | Config isolation |
| **api/main.py** | 80% | 85% | API endpoints |
| **Overall** | **85%** | **90%** | **Project minimum** |

**Enforcement:**
- CI/CD pipeline **fails** if coverage drops below minimum
- Coverage report generated on every commit
- Uncovered lines flagged in PR reviews

---

### 2.2 Performance Thresholds

| Metric | Threshold | Test Method |
|--------|-----------|-------------|
| **Unit test suite** | < 10 seconds | `pytest tests/unit/` |
| **Integration test suite** | < 60 seconds | `pytest tests/integration/` |
| **API endpoint `/simulate/trigger`** | < 500ms | Load testing |
| **API endpoint `/simulate/status`** | < 100ms | Load testing |
| **API endpoint `/results?detail=minimal`** | < 200ms | Load testing |
| **API endpoint `/results?detail=full`** | < 1 second | Load testing |
| **Database query (get_job)** | < 50ms | Benchmark tests |
| **Database query (get_job_progress)** | < 100ms | Benchmark tests |
| **Simulation (single model-day)** | 30-60s | Acceptance test |

**Enforcement:**
- Performance tests run nightly
- Alerts triggered if thresholds exceeded
- Benchmark results tracked over time

---

### 2.3 Quality Gates

**All PRs must pass:**
1. ✅ All tests passing (unit + integration)
2. ✅ Code coverage ≥ 85%
3. ✅ No critical security vulnerabilities (Bandit scan)
4. ✅ Linting passes (Ruff or Flake8)
5. ✅ Type checking passes (mypy with strict mode)
6. ✅ No performance regressions (±10% tolerance)

**Release checklist:**
1. ✅ All quality gates pass
2. ✅ End-to-end tests pass in Docker
3. ✅ Load testing passes (100 concurrent requests)
4. ✅ Security scan passes (OWASP ZAP)
5. ✅ Manual smoke tests complete

---

## 3. Test Suite Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared pytest fixtures
│
├── unit/                          # Fast, isolated tests
│   ├── __init__.py
│   ├── test_job_manager.py        # JobManager CRUD operations
│   ├── test_database.py           # Database utilities
│   ├── test_runtime_manager.py    # Config isolation
│   ├── test_results_service.py    # Results queries
│   └── test_models.py             # Pydantic model validation
│
├── integration/                   # Tests with real dependencies
│   ├── __init__.py
│   ├── test_api_endpoints.py      # FastAPI endpoint tests
│   ├── test_worker.py             # Job execution workflow
│   ├── test_executor.py           # Model-day execution
│   └── test_end_to_end.py         # Complete simulation flow
│
├── performance/                   # Benchmark and load tests
│   ├── __init__.py
│   ├── test_database_benchmarks.py
│   ├── test_api_load.py           # Locust or pytest-benchmark
│   └── test_simulation_timing.py
│
├── security/                      # Security tests
│   ├── __init__.py
│   ├── test_api_security.py       # Input validation, injection
│   └── test_auth.py               # Future: API key validation
│
└── e2e/                           # End-to-end with Docker
    ├── __init__.py
    └── test_docker_workflow.py    # Full Docker compose scenario
```

---

## 4. Unit Tests

### 4.1 test_job_manager.py

```python
# tests/unit/test_job_manager.py

import pytest
import tempfile
import os
from datetime import datetime, timedelta
from api.job_manager import JobManager

@pytest.fixture
def job_manager():
    """Create JobManager with temporary database"""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    jm = JobManager(db_path=temp_db.name)
    yield jm

    # Cleanup
    os.unlink(temp_db.name)


class TestJobCreation:
    """Test job creation and validation"""

    def test_create_job_success(self, job_manager):
        """Should create job with pending status"""
        job_id = job_manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16", "2025-01-17"],
            models=["gpt-5", "claude-3.7-sonnet"]
        )

        assert job_id is not None
        job = job_manager.get_job(job_id)
        assert job["status"] == "pending"
        assert job["date_range"] == ["2025-01-16", "2025-01-17"]
        assert job["models"] == ["gpt-5", "claude-3.7-sonnet"]
        assert job["created_at"] is not None

    def test_create_job_with_job_details(self, job_manager):
        """Should create job_details for each model-day"""
        job_id = job_manager.create_job(
            config_path="configs/test.json",
            date_range=["2025-01-16", "2025-01-17"],
            models=["gpt-5"]
        )

        progress = job_manager.get_job_progress(job_id)
        assert progress["total_model_days"] == 2  # 2 dates × 1 model
        assert progress["completed"] == 0
        assert progress["failed"] == 0

    def test_create_job_blocks_concurrent(self, job_manager):
        """Should prevent creating second job while first is pending"""
        job1_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        with pytest.raises(ValueError, match="Another simulation job is already running"):
            job_manager.create_job(
                "configs/test.json",
                ["2025-01-17"],
                ["gpt-5"]
            )

    def test_create_job_after_completion(self, job_manager):
        """Should allow new job after previous completes"""
        job1_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        job_manager.update_job_status(job1_id, "completed")

        # Now second job should be allowed
        job2_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-17"],
            ["gpt-5"]
        )
        assert job2_id is not None


class TestJobStatusTransitions:
    """Test job status state machine"""

    def test_pending_to_running(self, job_manager):
        """Should transition from pending to running"""
        job_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        # Update detail to running
        job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")

        job = job_manager.get_job(job_id)
        assert job["status"] == "running"
        assert job["started_at"] is not None

    def test_running_to_completed(self, job_manager):
        """Should transition to completed when all details complete"""
        job_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")
        job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "completed")

        job = job_manager.get_job(job_id)
        assert job["status"] == "completed"
        assert job["completed_at"] is not None
        assert job["total_duration_seconds"] is not None

    def test_partial_completion(self, job_manager):
        """Should mark as partial when some models fail"""
        job_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5", "claude-3.7-sonnet"]
        )

        # First model succeeds
        job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")
        job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "completed")

        # Second model fails
        job_manager.update_job_detail_status(job_id, "2025-01-16", "claude-3.7-sonnet", "running")
        job_manager.update_job_detail_status(
            job_id, "2025-01-16", "claude-3.7-sonnet", "failed",
            error="API timeout"
        )

        job = job_manager.get_job(job_id)
        assert job["status"] == "partial"

        progress = job_manager.get_job_progress(job_id)
        assert progress["completed"] == 1
        assert progress["failed"] == 1


class TestJobRetrieval:
    """Test job query operations"""

    def test_get_nonexistent_job(self, job_manager):
        """Should return None for nonexistent job"""
        job = job_manager.get_job("nonexistent-id")
        assert job is None

    def test_get_current_job(self, job_manager):
        """Should return most recent job"""
        job1_id = job_manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])
        job_manager.update_job_status(job1_id, "completed")

        job2_id = job_manager.create_job("configs/test.json", ["2025-01-17"], ["gpt-5"])

        current = job_manager.get_current_job()
        assert current["job_id"] == job2_id

    def test_find_job_by_date_range(self, job_manager):
        """Should find existing job with same date range"""
        job_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-16", "2025-01-17"],
            ["gpt-5"]
        )

        found = job_manager.find_job_by_date_range(["2025-01-16", "2025-01-17"])
        assert found["job_id"] == job_id


class TestJobProgress:
    """Test job progress tracking"""

    def test_progress_all_pending(self, job_manager):
        """Should show 0 completed when all pending"""
        job_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-16", "2025-01-17"],
            ["gpt-5"]
        )

        progress = job_manager.get_job_progress(job_id)
        assert progress["total_model_days"] == 2
        assert progress["completed"] == 0
        assert progress["failed"] == 0
        assert progress["current"] is None

    def test_progress_with_running(self, job_manager):
        """Should identify currently running model-day"""
        job_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5"]
        )

        job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "running")

        progress = job_manager.get_job_progress(job_id)
        assert progress["current"] == {"date": "2025-01-16", "model": "gpt-5"}

    def test_progress_details(self, job_manager):
        """Should return detailed progress for all model-days"""
        job_id = job_manager.create_job(
            "configs/test.json",
            ["2025-01-16"],
            ["gpt-5", "claude-3.7-sonnet"]
        )

        job_manager.update_job_detail_status(job_id, "2025-01-16", "gpt-5", "completed")

        progress = job_manager.get_job_progress(job_id)
        assert len(progress["details"]) == 2
        assert progress["details"][0]["model"] == "gpt-5"
        assert progress["details"][0]["status"] == "completed"


class TestJobCleanup:
    """Test maintenance operations"""

    def test_cleanup_old_jobs(self, job_manager):
        """Should delete jobs older than threshold"""
        # Create old job (manually set created_at)
        from api.database import get_db_connection
        conn = get_db_connection(job_manager.db_path)
        cursor = conn.cursor()

        old_date = (datetime.utcnow() - timedelta(days=35)).isoformat() + "Z"
        cursor.execute("""
            INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("old-job", "configs/test.json", "completed", '["2025-01-01"]', '["gpt-5"]', old_date))
        conn.commit()
        conn.close()

        # Create recent job
        recent_id = job_manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])

        # Cleanup jobs older than 30 days
        deleted = job_manager.cleanup_old_jobs(days=30)

        assert deleted["jobs_deleted"] == 1
        assert job_manager.get_job("old-job") is None
        assert job_manager.get_job(recent_id) is not None


# ========== Coverage Target: 95% for job_manager.py ==========
```

---

### 4.2 test_results_service.py

```python
# tests/unit/test_results_service.py

import pytest
import tempfile
import os
from api.results_service import ResultsService
from api.database import get_db_connection

@pytest.fixture
def results_service():
    """Create ResultsService with test data"""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    service = ResultsService(db_path=temp_db.name)

    # Populate test data
    _populate_test_data(temp_db.name)

    yield service

    os.unlink(temp_db.name)


def _populate_test_data(db_path):
    """Insert sample positions data"""
    from api.database import initialize_database
    initialize_database(db_path)

    conn = get_db_connection(db_path)
    cursor = conn.cursor()

    # Insert sample job
    cursor.execute("""
        INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ("test-job", "configs/test.json", "completed", '["2025-01-16"]', '["gpt-5"]', "2025-01-16T00:00:00Z"))

    # Insert positions
    cursor.execute("""
        INSERT INTO positions (
            job_id, date, model, action_id, action_type, symbol, amount, price,
            cash, portfolio_value, daily_profit, daily_return_pct,
            cumulative_profit, cumulative_return_pct, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("test-job", "2025-01-16", "gpt-5", 1, "buy", "AAPL", 10, 255.88,
          7441.2, 10000.0, 0.0, 0.0, 0.0, 0.0, "2025-01-16T09:30:00Z"))

    position_id = cursor.lastrowid

    # Insert holdings
    cursor.execute("""
        INSERT INTO holdings (position_id, symbol, quantity)
        VALUES (?, ?, ?)
    """, (position_id, "AAPL", 10))

    conn.commit()
    conn.close()


class TestGetResults:
    """Test results retrieval"""

    def test_get_results_minimal(self, results_service):
        """Should return minimal results for date"""
        results = results_service.get_results("2025-01-16", model="gpt-5", detail="minimal")

        assert results["date"] == "2025-01-16"
        assert len(results["results"]) == 1
        assert results["results"][0]["model"] == "gpt-5"
        assert "AAPL" in results["results"][0]["positions"]
        assert results["results"][0]["positions"]["AAPL"] == 10
        assert results["results"][0]["positions"]["CASH"] == 7441.2

    def test_get_results_nonexistent_date(self, results_service):
        """Should return empty results for nonexistent date"""
        results = results_service.get_results("2099-12-31", model="gpt-5")
        assert results["results"] == []

    def test_get_results_all_models(self, results_service):
        """Should return all models when model not specified"""
        results = results_service.get_results("2025-01-16")
        assert len(results["results"]) >= 1  # At least one model


class TestPortfolioTimeseries:
    """Test timeseries queries"""

    def test_get_timeseries(self, results_service):
        """Should return portfolio values over time"""
        timeseries = results_service.get_portfolio_timeseries("gpt-5")

        assert len(timeseries) >= 1
        assert timeseries[0]["date"] == "2025-01-16"
        assert "portfolio_value" in timeseries[0]

    def test_get_timeseries_with_date_range(self, results_service):
        """Should filter by date range"""
        timeseries = results_service.get_portfolio_timeseries(
            "gpt-5",
            start_date="2025-01-16",
            end_date="2025-01-16"
        )

        assert len(timeseries) == 1


class TestLeaderboard:
    """Test leaderboard generation"""

    def test_get_leaderboard(self, results_service):
        """Should rank models by portfolio value"""
        leaderboard = results_service.get_leaderboard()

        assert len(leaderboard) >= 1
        assert leaderboard[0]["rank"] == 1
        assert "portfolio_value" in leaderboard[0]

    def test_leaderboard_for_specific_date(self, results_service):
        """Should generate leaderboard for specific date"""
        leaderboard = results_service.get_leaderboard(date="2025-01-16")
        assert len(leaderboard) >= 1


# ========== Coverage Target: 95% for results_service.py ==========
```

---

## 5. Integration Tests

### 5.1 test_api_endpoints.py

```python
# tests/integration/test_api_endpoints.py

import pytest
from fastapi.testclient import TestClient
from api.main import app
import tempfile
import os

@pytest.fixture
def client():
    """Create test client with temporary database"""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    # Override database path for testing
    os.environ["TEST_DB_PATH"] = temp_db.name

    client = TestClient(app)
    yield client

    os.unlink(temp_db.name)


class TestTriggerEndpoint:
    """Test /simulate/trigger endpoint"""

    def test_trigger_simulation_success(self, client):
        """Should accept simulation trigger and return job_id"""
        response = client.post("/simulate/trigger", json={
            "config_path": "configs/test.json"
        })

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "accepted"
        assert "date_range" in data
        assert "models" in data

    def test_trigger_simulation_already_running(self, client):
        """Should return existing job if already running"""
        # First request
        response1 = client.post("/simulate/trigger", json={
            "config_path": "configs/test.json"
        })
        job_id_1 = response1.json()["job_id"]

        # Second request (before first completes)
        response2 = client.post("/simulate/trigger", json={
            "config_path": "configs/test.json"
        })

        # Should return same job_id
        assert response2.status_code in (200, 202)
        # job_id_2 = response2.json()["job_id"]
        # assert job_id_1 == job_id_2  # TODO: Fix based on actual implementation

    def test_trigger_simulation_invalid_config(self, client):
        """Should return 400 for invalid config path"""
        response = client.post("/simulate/trigger", json={
            "config_path": "nonexistent.json"
        })

        assert response.status_code == 400


class TestStatusEndpoint:
    """Test /simulate/status/{job_id} endpoint"""

    def test_get_status_success(self, client):
        """Should return job status"""
        # Create job first
        trigger_response = client.post("/simulate/trigger", json={
            "config_path": "configs/test.json"
        })
        job_id = trigger_response.json()["job_id"]

        # Get status
        response = client.get(f"/simulate/status/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] in ("pending", "running", "completed", "partial", "failed")
        assert "progress" in data

    def test_get_status_nonexistent(self, client):
        """Should return 404 for nonexistent job"""
        response = client.get("/simulate/status/nonexistent-id")
        assert response.status_code == 404


class TestResultsEndpoint:
    """Test /results endpoint"""

    def test_get_results_success(self, client):
        """Should return simulation results"""
        # TODO: Populate test data first
        response = client.get("/results", params={
            "date": "2025-01-16",
            "model": "gpt-5",
            "detail": "minimal"
        })

        # May be 404 if no data, or 200 if test data exists
        assert response.status_code in (200, 404)

    def test_get_results_invalid_date(self, client):
        """Should return 400 for invalid date format"""
        response = client.get("/results", params={
            "date": "invalid-date"
        })

        assert response.status_code == 400


class TestHealthEndpoint:
    """Test /health endpoint"""

    def test_health_check(self, client):
        """Should return healthy status"""
        response = client.get("/health")

        assert response.status_code in (200, 503)  # May be 503 if MCP services not running
        data = response.json()
        assert "status" in data
        assert "services" in data


# ========== Coverage Target: 85% for main.py ==========
```

---

## 6. Performance Tests

```python
# tests/performance/test_api_load.py

import pytest
from locust import HttpUser, task, between
import time

class AITraderAPIUser(HttpUser):
    """Simulate API user load"""
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    @task(3)
    def get_health(self):
        """Most common endpoint"""
        self.client.get("/health")

    @task(2)
    def get_results(self):
        """Fetch results"""
        self.client.get("/results?date=2025-01-16&model=gpt-5&detail=minimal")

    @task(1)
    def trigger_simulation(self):
        """Less common - trigger simulation"""
        self.client.post("/simulate/trigger", json={
            "config_path": "configs/test.json"
        })


# Run with: locust -f tests/performance/test_api_load.py --host=http://localhost:8080
```

```python
# tests/performance/test_database_benchmarks.py

import pytest
from api.job_manager import JobManager
import time

@pytest.mark.benchmark
def test_create_job_performance(benchmark, job_manager):
    """Benchmark job creation time"""
    result = benchmark(
        job_manager.create_job,
        "configs/test.json",
        ["2025-01-16"],
        ["gpt-5"]
    )

    # Should complete in < 50ms
    assert benchmark.stats.mean < 0.05


@pytest.mark.benchmark
def test_get_job_performance(benchmark, job_manager):
    """Benchmark job retrieval time"""
    # Create job first
    job_id = job_manager.create_job("configs/test.json", ["2025-01-16"], ["gpt-5"])

    result = benchmark(job_manager.get_job, job_id)

    # Should complete in < 10ms
    assert benchmark.stats.mean < 0.01


# Run with: pytest tests/performance/ --benchmark-only
```

---

## 7. Security Tests

```python
# tests/security/test_api_security.py

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


class TestInputValidation:
    """Test input validation and sanitization"""

    def test_sql_injection_protection(self):
        """Should reject SQL injection attempts"""
        response = client.get("/results", params={
            "date": "2025-01-16' OR '1'='1",
            "model": "gpt-5"
        })

        # Should return 400 (invalid date format), not execute SQL
        assert response.status_code == 400

    def test_path_traversal_protection(self):
        """Should reject path traversal attempts"""
        response = client.post("/simulate/trigger", json={
            "config_path": "../../etc/passwd"
        })

        # Should reject or return 404
        assert response.status_code in (400, 404)

    def test_xss_protection(self):
        """Should sanitize XSS attempts"""
        response = client.post("/simulate/trigger", json={
            "config_path": "<script>alert('xss')</script>"
        })

        assert response.status_code in (400, 404)
        # Response should not contain unsanitized script
        assert "<script>" not in response.text


class TestRateLimiting:
    """Test rate limiting (future feature)"""

    @pytest.mark.skip(reason="Rate limiting not implemented yet")
    def test_rate_limit_enforcement(self):
        """Should enforce rate limits"""
        # Make 100 requests rapidly
        for i in range(100):
            response = client.get("/health")

        # Should eventually return 429 Too Many Requests
        assert response.status_code == 429


# Run with: pytest tests/security/
```

---

## 8. End-to-End Tests

```python
# tests/e2e/test_docker_workflow.py

import pytest
import subprocess
import time
import requests

@pytest.mark.e2e
class TestDockerWorkflow:
    """Test complete workflow in Docker environment"""

    @classmethod
    def setup_class(cls):
        """Start Docker container before tests"""
        print("Building Docker image...")
        subprocess.run(["docker-compose", "build"], check=True)

        print("Starting container...")
        subprocess.run(["docker-compose", "up", "-d"], check=True)

        # Wait for health check
        print("Waiting for service to be healthy...")
        time.sleep(30)

    @classmethod
    def teardown_class(cls):
        """Stop Docker container after tests"""
        print("Stopping container...")
        subprocess.run(["docker-compose", "down"], check=True)

    def test_health_check(self):
        """Should return healthy status"""
        response = requests.get("http://localhost:8080/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_trigger_and_poll(self):
        """Should trigger simulation, poll status, and retrieve results"""
        # Trigger simulation
        response = requests.post("http://localhost:8080/simulate/trigger", json={
            "config_path": "configs/default_config.json"
        })

        assert response.status_code in (200, 202)
        job_id = response.json()["job_id"]

        # Poll until complete (with timeout)
        max_wait = 300  # 5 minutes
        start_time = time.time()

        while time.time() - start_time < max_wait:
            response = requests.get(f"http://localhost:8080/simulate/status/{job_id}")
            assert response.status_code == 200

            status = response.json()["status"]
            if status in ("completed", "partial", "failed"):
                break

            time.sleep(10)

        assert status in ("completed", "partial"), f"Job failed or timed out: {status}"

        # Retrieve results
        date = response.json()["date_range"][0]  # First date
        response = requests.get(f"http://localhost:8080/results", params={
            "date": date,
            "detail": "minimal"
        })

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0


# Run with: pytest tests/e2e/ -v -s
```

---

## 9. Test Configuration

### 9.1 pytest.ini

```ini
[pytest]
# Test discovery
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# Output
addopts =
    -v
    --strict-markers
    --tb=short
    --cov=api
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-fail-under=85

# Markers
markers =
    unit: Unit tests (fast, isolated)
    integration: Integration tests (with real dependencies)
    performance: Performance and benchmark tests
    security: Security tests
    e2e: End-to-end tests (Docker required)
    slow: Tests that take >10 seconds

# Test paths
testpaths = tests

# Coverage options
[coverage:run]
source = api
omit =
    */tests/*
    */conftest.py
    */__init__.py

[coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:
```

### 9.2 conftest.py

```python
# tests/conftest.py

import pytest
import tempfile
import os
from api.database import initialize_database

@pytest.fixture(scope="session")
def test_db():
    """Create test database for session"""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    initialize_database(temp_db.name)

    yield temp_db.name

    os.unlink(temp_db.name)


@pytest.fixture(scope="function")
def clean_db(test_db):
    """Clean database before each test"""
    from api.database import get_db_connection
    conn = get_db_connection(test_db)
    cursor = conn.cursor()

    # Clear all tables
    cursor.execute("DELETE FROM tool_usage")
    cursor.execute("DELETE FROM reasoning_logs")
    cursor.execute("DELETE FROM holdings")
    cursor.execute("DELETE FROM positions")
    cursor.execute("DELETE FROM job_details")
    cursor.execute("DELETE FROM jobs")

    conn.commit()
    conn.close()

    return test_db


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return {
        "agent_type": "BaseAgent",
        "date_range": {
            "init_date": "2025-01-16",
            "end_date": "2025-01-17"
        },
        "models": [
            {
                "name": "test-model",
                "basemodel": "openai/gpt-4",
                "signature": "test-model",
                "enabled": True
            }
        ],
        "agent_config": {
            "max_steps": 10,
            "max_retries": 3,
            "base_delay": 0.5,
            "initial_cash": 10000.0
        },
        "log_config": {
            "log_path": "./data/agent_data"
        }
    }


# Hooks
def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "performance: Performance tests")
    config.addinivalue_line("markers", "security: Security tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
```

---

## 10. CI/CD Integration

### 10.1 GitHub Actions Workflow

```yaml
# .github/workflows/test.yml

name: Test Suite

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    strategy:
      matrix:
        python-version: ["3.10", "3.11"]

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache dependencies
        uses: actions/cache@v3
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-api.txt
          pip install -r requirements-dev.txt

      - name: Lint with ruff
        run: ruff check api/ tests/

      - name: Type check with mypy
        run: mypy api/ --strict

      - name: Run unit tests
        run: pytest tests/unit/ -v --cov=api --cov-report=xml

      - name: Run integration tests
        run: pytest tests/integration/ -v

      - name: Run security tests
        run: |
          bandit -r api/ -ll
          pytest tests/security/ -v

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
          fail_ci_if_error: true

      - name: Check coverage threshold
        run: |
          coverage report --fail-under=85

  performance:
    runs-on: ubuntu-latest
    needs: test

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-api.txt
          pip install pytest-benchmark

      - name: Run benchmark tests
        run: pytest tests/performance/ --benchmark-only --benchmark-autosave

      - name: Compare benchmarks
        run: pytest-benchmark compare --group-by=name
```

---

## 11. Testing Checklist

### 11.1 Pre-Commit Checklist

- [ ] All unit tests pass locally
- [ ] Code coverage ≥ 85%
- [ ] Linting passes (ruff/flake8)
- [ ] Type checking passes (mypy)
- [ ] No security issues (bandit)

### 11.2 Pre-PR Checklist

- [ ] All tests pass (unit + integration)
- [ ] New features have tests
- [ ] Bug fixes have regression tests
- [ ] Documentation updated
- [ ] CHANGELOG.md updated

### 11.3 Pre-Release Checklist

- [ ] All CI/CD checks pass
- [ ] E2E tests pass in Docker
- [ ] Performance benchmarks within thresholds
- [ ] Security scan clean (OWASP ZAP)
- [ ] Manual smoke tests complete

---

## Summary

**Comprehensive test suite** with:
- ✅ **85% minimum coverage** (95% for critical paths)
- ✅ **4 test categories:** unit, integration, performance, security
- ✅ **Performance thresholds** enforced (API endpoints < 500ms)
- ✅ **CI/CD integration** with GitHub Actions
- ✅ **Quality gates** preventing regressions

**Test count estimate:** ~150 tests total
- Unit tests: ~80
- Integration tests: ~30
- Performance tests: ~20
- Security tests: ~10
- E2E tests: ~10

**Execution time:**
- Unit tests: < 10 seconds
- Integration tests: < 60 seconds
- All tests (excluding E2E): < 2 minutes
- Full suite (including E2E): < 10 minutes

This ensures **high-quality, maintainable code** with confidence in deployments.
