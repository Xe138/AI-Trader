from api.main import SimulateTriggerResponse, JobStatusResponse, JobProgress

def test_simulate_trigger_response_accepts_warnings():
    """Test SimulateTriggerResponse accepts warnings field."""
    response = SimulateTriggerResponse(
        job_id="test-123",
        status="completed",
        total_model_days=10,
        message="Job completed",
        deployment_mode="DEV",
        is_dev_mode=True,
        warnings=["Rate limited", "Skipped 2 dates"]
    )

    assert response.warnings == ["Rate limited", "Skipped 2 dates"]

def test_job_status_response_accepts_warnings():
    """Test JobStatusResponse accepts warnings field."""
    response = JobStatusResponse(
        job_id="test-123",
        status="completed",
        progress=JobProgress(total_model_days=10, completed=10, failed=0, pending=0),
        date_range=["2025-10-01"],
        models=["gpt-5"],
        created_at="2025-11-01T00:00:00Z",
        details=[],
        deployment_mode="DEV",
        is_dev_mode=True,
        warnings=["Rate limited"]
    )

    assert response.warnings == ["Rate limited"]
