"""
Unit tests for api/models.py - Pydantic data models.

Coverage target: 90%+

Tests verify:
- Request model validation
- Response model serialization
- Field constraints and types
- Optional vs required fields
"""

import pytest
from pydantic import ValidationError
from datetime import datetime


@pytest.mark.unit
class TestTriggerSimulationRequest:
    """Test TriggerSimulationRequest model."""

    def test_valid_request_with_defaults(self):
        """Should accept request with default config_path."""
        from api.models import TriggerSimulationRequest

        request = TriggerSimulationRequest()
        assert request.config_path == "configs/default_config.json"

    def test_valid_request_with_custom_path(self):
        """Should accept request with custom config_path."""
        from api.models import TriggerSimulationRequest

        request = TriggerSimulationRequest(config_path="configs/custom.json")
        assert request.config_path == "configs/custom.json"


@pytest.mark.unit
class TestJobProgress:
    """Test JobProgress model."""

    def test_valid_progress_minimal(self):
        """Should create progress with minimal fields."""
        from api.models import JobProgress

        progress = JobProgress(
            total_model_days=4,
            completed=2,
            failed=0
        )

        assert progress.total_model_days == 4
        assert progress.completed == 2
        assert progress.failed == 0
        assert progress.current is None
        assert progress.details is None

    def test_valid_progress_with_current(self):
        """Should include current model-day being executed."""
        from api.models import JobProgress

        progress = JobProgress(
            total_model_days=4,
            completed=1,
            failed=0,
            current={"date": "2025-01-16", "model": "gpt-5"}
        )

        assert progress.current == {"date": "2025-01-16", "model": "gpt-5"}

    def test_valid_progress_with_details(self):
        """Should include detailed progress for all model-days."""
        from api.models import JobProgress

        details = [
            {"date": "2025-01-16", "model": "gpt-5", "status": "completed", "duration_seconds": 45.2},
            {"date": "2025-01-16", "model": "claude", "status": "running", "duration_seconds": None}
        ]

        progress = JobProgress(
            total_model_days=2,
            completed=1,
            failed=0,
            details=details
        )

        assert len(progress.details) == 2
        assert progress.details[0]["status"] == "completed"


@pytest.mark.unit
class TestTriggerSimulationResponse:
    """Test TriggerSimulationResponse model."""

    def test_valid_response_accepted(self):
        """Should create accepted response."""
        from api.models import TriggerSimulationResponse

        response = TriggerSimulationResponse(
            job_id="test-job-123",
            status="accepted",
            date_range=["2025-01-16", "2025-01-17"],
            models=["gpt-5"],
            created_at="2025-01-20T14:30:00Z",
            message="Job queued successfully"
        )

        assert response.job_id == "test-job-123"
        assert response.status == "accepted"
        assert len(response.date_range) == 2
        assert response.progress is None

    def test_valid_response_with_progress(self):
        """Should include progress for running jobs."""
        from api.models import TriggerSimulationResponse, JobProgress

        progress = JobProgress(
            total_model_days=4,
            completed=2,
            failed=0
        )

        response = TriggerSimulationResponse(
            job_id="test-job-123",
            status="running",
            date_range=["2025-01-16"],
            models=["gpt-5"],
            created_at="2025-01-20T14:30:00Z",
            message="Simulation in progress",
            progress=progress
        )

        assert response.progress is not None
        assert response.progress.completed == 2


@pytest.mark.unit
class TestJobStatusResponse:
    """Test JobStatusResponse model."""

    def test_valid_status_running(self):
        """Should create running status response."""
        from api.models import JobStatusResponse, JobProgress

        progress = JobProgress(
            total_model_days=4,
            completed=2,
            failed=0,
            current={"date": "2025-01-16", "model": "gpt-5"}
        )

        response = JobStatusResponse(
            job_id="test-job-123",
            status="running",
            date_range=["2025-01-16", "2025-01-17"],
            models=["gpt-5", "claude"],
            progress=progress,
            created_at="2025-01-20T14:30:00Z"
        )

        assert response.status == "running"
        assert response.completed_at is None
        assert response.total_duration_seconds is None

    def test_valid_status_completed(self):
        """Should create completed status response."""
        from api.models import JobStatusResponse, JobProgress

        progress = JobProgress(
            total_model_days=4,
            completed=4,
            failed=0
        )

        response = JobStatusResponse(
            job_id="test-job-123",
            status="completed",
            date_range=["2025-01-16"],
            models=["gpt-5"],
            progress=progress,
            created_at="2025-01-20T14:30:00Z",
            completed_at="2025-01-20T14:35:00Z",
            total_duration_seconds=300.5
        )

        assert response.status == "completed"
        assert response.completed_at == "2025-01-20T14:35:00Z"
        assert response.total_duration_seconds == 300.5


@pytest.mark.unit
class TestDailyPnL:
    """Test DailyPnL model."""

    def test_valid_pnl(self):
        """Should create P&L with all fields."""
        from api.models import DailyPnL

        pnl = DailyPnL(
            profit=150.50,
            return_pct=1.51,
            portfolio_value=10150.50
        )

        assert pnl.profit == 150.50
        assert pnl.return_pct == 1.51
        assert pnl.portfolio_value == 10150.50


@pytest.mark.unit
class TestTrade:
    """Test Trade model."""

    def test_valid_trade_buy(self):
        """Should create buy trade."""
        from api.models import Trade

        trade = Trade(
            id=1,
            action="buy",
            symbol="AAPL",
            amount=10,
            price=255.88,
            total=2558.80
        )

        assert trade.action == "buy"
        assert trade.symbol == "AAPL"
        assert trade.amount == 10

    def test_valid_trade_sell(self):
        """Should create sell trade."""
        from api.models import Trade

        trade = Trade(
            id=2,
            action="sell",
            symbol="MSFT",
            amount=5
        )

        assert trade.action == "sell"
        assert trade.price is None  # Optional
        assert trade.total is None  # Optional


@pytest.mark.unit
class TestAIReasoning:
    """Test AIReasoning model."""

    def test_valid_reasoning(self):
        """Should create reasoning summary."""
        from api.models import AIReasoning

        reasoning = AIReasoning(
            total_steps=15,
            stop_signal_received=True,
            reasoning_summary="Market analysis shows...",
            tool_usage={"search": 3, "get_price": 5, "trade": 1}
        )

        assert reasoning.total_steps == 15
        assert reasoning.stop_signal_received is True
        assert "search" in reasoning.tool_usage


@pytest.mark.unit
class TestModelResult:
    """Test ModelResult model."""

    def test_valid_result_minimal(self):
        """Should create minimal result."""
        from api.models import ModelResult, DailyPnL

        pnl = DailyPnL(profit=150.0, return_pct=1.5, portfolio_value=10150.0)

        result = ModelResult(
            model="gpt-5",
            positions={"AAPL": 10, "CASH": 7500.0},
            daily_pnl=pnl
        )

        assert result.model == "gpt-5"
        assert result.positions["AAPL"] == 10
        assert result.trades is None
        assert result.ai_reasoning is None

    def test_valid_result_full(self):
        """Should create full result with all details."""
        from api.models import ModelResult, DailyPnL, Trade, AIReasoning

        pnl = DailyPnL(profit=150.0, return_pct=1.5, portfolio_value=10150.0)
        trades = [Trade(id=1, action="buy", symbol="AAPL", amount=10)]
        reasoning = AIReasoning(
            total_steps=15,
            stop_signal_received=True,
            reasoning_summary="...",
            tool_usage={"search": 3}
        )

        result = ModelResult(
            model="gpt-5",
            positions={"AAPL": 10, "CASH": 7500.0},
            daily_pnl=pnl,
            trades=trades,
            ai_reasoning=reasoning,
            log_file_path="data/agent_data/gpt-5/log/2025-01-16/log.jsonl"
        )

        assert result.trades is not None
        assert len(result.trades) == 1
        assert result.ai_reasoning is not None


@pytest.mark.unit
class TestResultsResponse:
    """Test ResultsResponse model."""

    def test_valid_results_response(self):
        """Should create results response."""
        from api.models import ResultsResponse, ModelResult, DailyPnL

        pnl = DailyPnL(profit=150.0, return_pct=1.5, portfolio_value=10150.0)
        model_result = ModelResult(
            model="gpt-5",
            positions={"AAPL": 10, "CASH": 7500.0},
            daily_pnl=pnl
        )

        response = ResultsResponse(
            date="2025-01-16",
            results=[model_result]
        )

        assert response.date == "2025-01-16"
        assert len(response.results) == 1
        assert response.results[0].model == "gpt-5"


@pytest.mark.unit
class TestResultsQueryParams:
    """Test ResultsQueryParams model."""

    def test_valid_params_minimal(self):
        """Should create params with minimal fields."""
        from api.models import ResultsQueryParams

        params = ResultsQueryParams(date="2025-01-16")

        assert params.date == "2025-01-16"
        assert params.model is None
        assert params.detail == "minimal"

    def test_valid_params_with_filters(self):
        """Should create params with all filters."""
        from api.models import ResultsQueryParams

        params = ResultsQueryParams(
            date="2025-01-16",
            model="gpt-5",
            detail="full"
        )

        assert params.model == "gpt-5"
        assert params.detail == "full"

    def test_invalid_date_format(self):
        """Should reject invalid date format."""
        from api.models import ResultsQueryParams

        with pytest.raises(ValidationError):
            ResultsQueryParams(date="2025/01/16")  # Wrong format

    def test_invalid_detail_value(self):
        """Should reject invalid detail value."""
        from api.models import ResultsQueryParams

        with pytest.raises(ValidationError):
            ResultsQueryParams(date="2025-01-16", detail="invalid")


# Coverage target: 90%+ for api/models.py
