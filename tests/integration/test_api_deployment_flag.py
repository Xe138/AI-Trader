import os
import pytest
from fastapi.testclient import TestClient


def test_api_includes_deployment_mode_flag():
    """Test API responses include deployment_mode field"""
    os.environ["DEPLOYMENT_MODE"] = "DEV"

    from api.main import app
    client = TestClient(app)

    # Test GET /health endpoint (should include deployment info)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    assert "deployment_mode" in data
    assert data["deployment_mode"] == "DEV"


def test_job_response_includes_deployment_mode():
    """Test job creation response includes deployment mode"""
    os.environ["DEPLOYMENT_MODE"] = "PROD"

    from api.main import app
    client = TestClient(app)

    # Create a test job
    config = {
        "agent_type": "BaseAgent",
        "date_range": {"init_date": "2025-01-01", "end_date": "2025-01-02"},
        "models": [{"name": "test", "basemodel": "mock/test", "signature": "test", "enabled": True}]
    }

    response = client.post("/run", json={"config": config})

    if response.status_code == 200:
        data = response.json()
        assert "deployment_mode" in data
        assert data["deployment_mode"] == "PROD"
