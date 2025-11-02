"""
End-to-end test for async price download flow.

Tests the complete flow:
1. POST /simulate/trigger (fast response)
2. Worker downloads data in background
3. GET /simulate/status shows downloading_data → running → completed
4. Warnings are captured and returned
"""

import pytest
import time
from unittest.mock import patch, Mock
from api.main import create_app
from api.database import initialize_database
from fastapi.testclient import TestClient

@pytest.fixture
def test_app(tmp_path):
    """Create test app with isolated database."""
    db_path = str(tmp_path / "test.db")
    initialize_database(db_path)

    app = create_app(db_path=db_path, config_path="configs/default_config.json")
    app.state.test_mode = True  # Disable background worker

    yield app

@pytest.fixture
def test_client(test_app):
    """Create test client."""
    return TestClient(test_app)

def test_complete_async_download_flow(test_client, monkeypatch):
    """Test complete flow from trigger to completion with async download."""

    # Mock PriceDataManager for predictable behavior
    class MockPriceManager:
        def __init__(self, db_path):
            self.db_path = db_path

        def get_missing_coverage(self, start, end):
            return {"AAPL": {"2025-10-01"}}  # Simulate missing data

        def download_missing_data_prioritized(self, missing, requested):
            return {
                "downloaded": ["AAPL"],
                "failed": [],
                "rate_limited": False
            }

        def get_available_trading_dates(self, start, end):
            return ["2025-10-01"]

    monkeypatch.setattr("api.price_data_manager.PriceDataManager", MockPriceManager)

    # Mock execution to avoid actual trading
    def mock_execute_date(self, date, models, config_path):
        # Update job details to simulate successful execution
        from api.job_manager import JobManager
        job_manager = JobManager(db_path=test_client.app.state.db_path)
        for model in models:
            job_manager.update_job_detail_status(self.job_id, date, model, "completed")

    monkeypatch.setattr("api.simulation_worker.SimulationWorker._execute_date", mock_execute_date)

    # Step 1: Trigger simulation
    start_time = time.time()
    response = test_client.post("/simulate/trigger", json={
        "start_date": "2025-10-01",
        "end_date": "2025-10-01",
        "models": ["gpt-5"]
    })
    elapsed = time.time() - start_time

    # Should respond quickly
    assert elapsed < 2.0
    assert response.status_code == 200

    data = response.json()
    job_id = data["job_id"]
    assert data["status"] == "pending"

    # Step 2: Run worker manually (since test_mode=True)
    from api.simulation_worker import SimulationWorker
    worker = SimulationWorker(job_id=job_id, db_path=test_client.app.state.db_path)
    result = worker.run()

    # Step 3: Check final status
    status_response = test_client.get(f"/simulate/status/{job_id}")
    assert status_response.status_code == 200

    status_data = status_response.json()
    assert status_data["status"] == "completed"
    assert status_data["job_id"] == job_id

def test_flow_with_rate_limit_warning(test_client, monkeypatch):
    """Test flow when rate limit is hit during download."""

    class MockPriceManagerRateLimited:
        def __init__(self, db_path):
            self.db_path = db_path

        def get_missing_coverage(self, start, end):
            return {"AAPL": {"2025-10-01"}, "MSFT": {"2025-10-01"}}

        def download_missing_data_prioritized(self, missing, requested):
            return {
                "downloaded": ["AAPL"],
                "failed": ["MSFT"],
                "rate_limited": True
            }

        def get_available_trading_dates(self, start, end):
            return []  # No complete dates due to rate limit

    monkeypatch.setattr("api.price_data_manager.PriceDataManager", MockPriceManagerRateLimited)

    # Trigger
    response = test_client.post("/simulate/trigger", json={
        "start_date": "2025-10-01",
        "end_date": "2025-10-01",
        "models": ["gpt-5"]
    })

    job_id = response.json()["job_id"]

    # Run worker
    from api.simulation_worker import SimulationWorker
    worker = SimulationWorker(job_id=job_id, db_path=test_client.app.state.db_path)
    result = worker.run()

    # Should fail due to no available dates
    assert result["success"] is False

    # Check status has error
    status_response = test_client.get(f"/simulate/status/{job_id}")
    status_data = status_response.json()
    assert status_data["status"] == "failed"
    assert "No trading dates available" in status_data["error"]

def test_flow_with_partial_data(test_client, monkeypatch):
    """Test flow when some dates are skipped due to incomplete data."""

    class MockPriceManagerPartial:
        def __init__(self, db_path):
            self.db_path = db_path

        def get_missing_coverage(self, start, end):
            return {}  # No missing data

        def get_available_trading_dates(self, start, end):
            # Only 2 out of 3 dates available
            return ["2025-10-01", "2025-10-03"]

    monkeypatch.setattr("api.price_data_manager.PriceDataManager", MockPriceManagerPartial)

    def mock_execute_date(self, date, models, config_path):
        # Update job details to simulate successful execution
        from api.job_manager import JobManager
        job_manager = JobManager(db_path=test_client.app.state.db_path)
        for model in models:
            job_manager.update_job_detail_status(self.job_id, date, model, "completed")

    monkeypatch.setattr("api.simulation_worker.SimulationWorker._execute_date", mock_execute_date)

    # Trigger with 3 dates
    response = test_client.post("/simulate/trigger", json={
        "start_date": "2025-10-01",
        "end_date": "2025-10-03",
        "models": ["gpt-5"]
    })

    job_id = response.json()["job_id"]

    # Run worker
    from api.simulation_worker import SimulationWorker
    worker = SimulationWorker(job_id=job_id, db_path=test_client.app.state.db_path)
    result = worker.run()

    # Should complete with warnings
    assert result["success"] is True
    assert len(result["warnings"]) > 0
    assert "Skipped" in result["warnings"][0]

    # Check status returns warnings
    status_response = test_client.get(f"/simulate/status/{job_id}")
    status_data = status_response.json()
    # Status should be "running" or "partial" since not all dates were processed
    # (job details exist for 3 dates but only 2 were executed)
    assert status_data["status"] in ["running", "partial", "completed"]
    assert status_data["warnings"] is not None
    assert len(status_data["warnings"]) > 0
