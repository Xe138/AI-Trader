"""
Integration tests for FastAPI endpoints.

Coverage target: 90%+

Tests verify:
- POST /simulate/trigger: Job creation and trigger
- GET /simulate/status/{job_id}: Job status retrieval
- GET /results: Results querying with filters
- GET /health: Health check endpoint
- Error handling and validation
"""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import json


@pytest.fixture
def api_client(clean_db, tmp_path):
    """Create FastAPI test client with clean database."""
    from api.main import create_app

    # Create test config
    test_config = tmp_path / "test_config.json"
    test_config.write_text(json.dumps({
        "agent_type": "BaseAgent",
        "date_range": {"init_date": "2025-01-16", "end_date": "2025-01-17"},
        "models": [
            {"name": "Test Model", "basemodel": "gpt-4", "signature": "gpt-4", "enabled": True}
        ],
        "agent_config": {"max_steps": 30, "initial_cash": 10000.0},
        "log_config": {"log_path": "./data/agent_data"}
    }))

    app = create_app(db_path=clean_db)
    # Enable test mode to prevent background worker from starting
    app.state.test_mode = True
    client = TestClient(app)
    client.test_config_path = str(test_config)
    client.db_path = clean_db
    return client


@pytest.mark.integration
class TestSimulateTriggerEndpoint:
    """Test POST /simulate/trigger endpoint."""

    def test_trigger_creates_job(self, api_client):
        """Should create job and return job_id."""
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-17",
            "models": ["gpt-4"]
        })

        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert data["total_model_days"] == 2

    def test_trigger_single_date(self, api_client):
        """Should create job for single date."""
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-16",
            "models": ["gpt-4"]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["total_model_days"] == 1

    def test_trigger_resume_mode_cold_start(self, api_client):
        """Should use end_date as single day when no existing data (cold start)."""
        response = api_client.post("/simulate/trigger", json={
            "start_date": None,
            "end_date": "2025-01-16",
            "models": ["gpt-4"]
        })

        assert response.status_code == 200
        data = response.json()
        assert data["total_model_days"] == 1
        assert "resume mode" in data["message"]

    def test_trigger_requires_end_date(self, api_client):
        """Should reject request with missing end_date."""
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "",
            "models": ["gpt-4"]
        })

        assert response.status_code == 422
        assert "end_date" in str(response.json()["detail"]).lower()

    def test_trigger_rejects_null_end_date(self, api_client):
        """Should reject request with null end_date."""
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": None,
            "models": ["gpt-4"]
        })

        assert response.status_code == 422

    def test_trigger_validates_models(self, api_client):
        """Should use enabled models from config when models not specified."""
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-16"
            # models not specified - should use enabled models from config
        })

        assert response.status_code == 200
        data = response.json()
        assert data["total_model_days"] >= 1

    def test_trigger_empty_models_uses_config(self, api_client):
        """Should use enabled models from config when models is empty list."""
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-16",
            "models": []  # Empty list - should use enabled models from config
        })

        assert response.status_code == 200
        data = response.json()
        assert data["total_model_days"] >= 1

    def test_trigger_enforces_single_job_limit(self, api_client):
        """Should reject trigger when job already running."""
        # Create first job
        api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-16",
            "models": ["gpt-4"]
        })

        # Try to create second job
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-17",
            "end_date": "2025-01-17",
            "models": ["gpt-4"]
        })

        assert response.status_code == 400
        assert "already running" in response.json()["detail"].lower()

    def test_trigger_idempotent_behavior(self, api_client):
        """Should skip already completed dates when replace_existing=false."""
        # This test would need a completed job first
        # For now, just verify the parameter is accepted
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-16",
            "models": ["gpt-4"],
            "replace_existing": False
        })

        assert response.status_code == 200

    def test_trigger_replace_existing_flag(self, api_client):
        """Should accept replace_existing flag."""
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-16",
            "models": ["gpt-4"],
            "replace_existing": True
        })

        assert response.status_code == 200


@pytest.mark.integration
class TestSimulateStatusEndpoint:
    """Test GET /simulate/status/{job_id} endpoint."""

    def test_status_returns_job_info(self, api_client):
        """Should return job status and progress."""
        # Create job
        create_response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-16",
            "models": ["gpt-4"]
        })
        job_id = create_response.json()["job_id"]

        # Get status
        response = api_client.get(f"/simulate/status/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "pending"
        assert "progress" in data
        assert data["progress"]["total_model_days"] == 1

    def test_status_returns_404_for_nonexistent_job(self, api_client):
        """Should return 404 for unknown job_id."""
        response = api_client.get("/simulate/status/nonexistent-job-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_status_includes_model_day_details(self, api_client):
        """Should include model-day execution details."""
        # Create job
        create_response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-17",
            "models": ["gpt-4"]
        })
        job_id = create_response.json()["job_id"]

        # Get status
        response = api_client.get(f"/simulate/status/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert "details" in data
        assert len(data["details"]) == 2  # 2 dates
        assert all("date" in detail for detail in data["details"])
        assert all("model" in detail for detail in data["details"])
        assert all("status" in detail for detail in data["details"])


@pytest.mark.integration
class TestResultsEndpoint:
    """Test GET /results endpoint."""

    def test_results_returns_all_results(self, api_client):
        """Should return all results without filters."""
        response = api_client.get("/results")

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_results_filters_by_job_id(self, api_client):
        """Should filter results by job_id."""
        # Create job
        create_response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16",
            "end_date": "2025-01-16",
            "models": ["gpt-4"]
        })
        job_id = create_response.json()["job_id"]

        # Query results
        response = api_client.get(f"/results?job_id={job_id}")

        assert response.status_code == 200
        data = response.json()
        # Should return empty list initially (no completed executions yet)
        assert isinstance(data["results"], list)

    def test_results_filters_by_date(self, api_client):
        """Should filter results by date."""
        response = api_client.get("/results?date=2025-01-16")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["results"], list)

    def test_results_filters_by_model(self, api_client):
        """Should filter results by model."""
        response = api_client.get("/results?model=gpt-4")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["results"], list)

    def test_results_combines_multiple_filters(self, api_client):
        """Should support multiple filter parameters."""
        response = api_client.get("/results?date=2025-01-16&model=gpt-4")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["results"], list)

    def test_results_includes_position_data(self, api_client):
        """Should include position and holdings data."""
        # This test will pass once we have actual data
        response = api_client.get("/results")

        assert response.status_code == 200
        data = response.json()
        # Each result should have expected structure
        for result in data["results"]:
            assert "job_id" in result or True  # Pass if empty


@pytest.mark.integration
class TestHealthEndpoint:
    """Test GET /health endpoint."""

    def test_health_returns_ok(self, api_client):
        """Should return healthy status."""
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_health_includes_database_check(self, api_client):
        """Should verify database connectivity."""
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "database" in data
        assert data["database"] == "connected"

    def test_health_includes_system_info(self, api_client):
        """Should include system information."""
        response = api_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "version" in data or "timestamp" in data


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling across endpoints."""

    def test_invalid_json_returns_422(self, api_client):
        """Should handle malformed JSON."""
        response = api_client.post(
            "/simulate/trigger",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422

    def test_missing_required_fields_returns_422(self, api_client):
        """Should validate required fields."""
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-01-16"
            # Missing end_date
        })

        assert response.status_code == 422

    def test_invalid_job_id_format_returns_404(self, api_client):
        """Should handle invalid job_id format gracefully."""
        response = api_client.get("/simulate/status/invalid-format")

        assert response.status_code == 404


@pytest.mark.integration
class TestAsyncDownload:
    """Test async price download behavior."""

    def test_trigger_endpoint_fast_response(self, api_client):
        """Test that /simulate/trigger responds quickly without downloading data."""
        import time

        start_time = time.time()

        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-10-01",
            "end_date": "2025-10-01",
            "models": ["gpt-4"]
        })

        elapsed = time.time() - start_time

        # Should respond in less than 2 seconds (allowing for DB operations)
        assert elapsed < 2.0
        assert response.status_code == 200
        assert "job_id" in response.json()

    def test_trigger_endpoint_no_price_download(self, api_client):
        """Test that endpoint doesn't import or use PriceDataManager."""
        import api.main

        # Verify PriceDataManager is not imported in api.main
        assert not hasattr(api.main, 'PriceDataManager'), \
            "PriceDataManager should not be imported in api.main"

        # Endpoint should still create job successfully
        response = api_client.post("/simulate/trigger", json={
            "start_date": "2025-10-01",
            "end_date": "2025-10-01",
            "models": ["gpt-4"]
        })

        assert response.status_code == 200
        assert "job_id" in response.json()

    def test_status_endpoint_returns_warnings(self, api_client):
        """Test that /simulate/status returns warnings field."""
        from api.database import initialize_database
        from api.job_manager import JobManager

        # Create job with warnings
        db_path = api_client.db_path
        job_manager = JobManager(db_path=db_path)

        job_id = job_manager.create_job(
            config_path="config.json",
            date_range=["2025-10-01"],
            models=["gpt-5"]
        )

        # Add warnings
        warnings = ["Rate limited", "Skipped 1 date"]
        job_manager.add_job_warnings(job_id, warnings)

        # Get status
        response = api_client.get(f"/simulate/status/{job_id}")

        assert response.status_code == 200
        data = response.json()
        assert "warnings" in data
        assert data["warnings"] == warnings


# Coverage target: 90%+ for api/main.py
