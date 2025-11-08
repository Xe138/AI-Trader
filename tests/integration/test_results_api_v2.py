import pytest
from fastapi.testclient import TestClient
from api.main import create_app
from api.database import Database
from api.routes.results_v2 import get_database


class TestResultsAPIV2:

    @pytest.fixture
    def client(self, db):
        """Create test client with overridden database dependency."""
        # Create fresh app instance
        app = create_app()
        # Override the database dependency
        app.dependency_overrides[get_database] = lambda: db
        client = TestClient(app)
        yield client
        # Clean up
        app.dependency_overrides.clear()

    @pytest.fixture
    def db(self, tmp_path):
        """Create test database with sample data."""
        import importlib
        migration_module = importlib.import_module('api.migrations.001_trading_days_schema')
        create_trading_days_schema = migration_module.create_trading_days_schema

        db_path = tmp_path / "test.db"
        db = Database(str(db_path))

        # Create schema
        db.connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT
            )
        """)
        create_trading_days_schema(db)

        # Insert sample data
        db.connection.execute(
            "INSERT INTO jobs (job_id, config_path, status, date_range, models, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("test-job", "config.json", "completed", '["2025-01-15", "2025-01-16"]', '["gpt-4"]', "2025-01-15T00:00:00Z")
        )

        # Day 1
        day1_id = db.create_trading_day(
            job_id="test-job",
            model="gpt-4",
            date="2025-01-15",
            starting_cash=10000.0,
            starting_portfolio_value=10000.0,
            daily_profit=0.0,
            daily_return_pct=0.0,
            ending_cash=8500.0,
            ending_portfolio_value=10000.0,
            reasoning_summary="First day summary",
            total_actions=1
        )
        db.create_holding(day1_id, "AAPL", 10)
        db.create_action(day1_id, "buy", "AAPL", 10, 150.0)

        db.connection.commit()
        return db

    def test_results_without_reasoning(self, client, db):
        """Test default response excludes reasoning."""
        response = client.get("/results?job_id=test-job&start_date=2025-01-15&end_date=2025-01-15")

        assert response.status_code == 200
        data = response.json()

        assert data["count"] == 1
        assert data["results"][0]["reasoning"] is None

    def test_results_with_summary(self, client, db):
        """Test including reasoning summary."""
        response = client.get("/results?job_id=test-job&start_date=2025-01-15&end_date=2025-01-15&reasoning=summary")

        data = response.json()
        result = data["results"][0]

        assert result["reasoning"] == "First day summary"

    def test_results_structure(self, client, db):
        """Test complete response structure."""
        response = client.get("/results?job_id=test-job&start_date=2025-01-15&end_date=2025-01-15")

        result = response.json()["results"][0]

        # Basic fields
        assert result["date"] == "2025-01-15"
        assert result["model"] == "gpt-4"
        assert result["job_id"] == "test-job"

        # Starting position
        assert "starting_position" in result
        assert result["starting_position"]["cash"] == 10000.0
        assert result["starting_position"]["portfolio_value"] == 10000.0
        assert result["starting_position"]["holdings"] == []  # First day

        # Daily metrics
        assert "daily_metrics" in result
        assert result["daily_metrics"]["profit"] == 0.0
        assert result["daily_metrics"]["return_pct"] == 0.0

        # Trades
        assert "trades" in result
        assert len(result["trades"]) == 1
        assert result["trades"][0]["action_type"] == "buy"
        assert result["trades"][0]["symbol"] == "AAPL"

        # Final position
        assert "final_position" in result
        assert result["final_position"]["cash"] == 8500.0
        assert result["final_position"]["portfolio_value"] == 10000.0
        assert len(result["final_position"]["holdings"]) == 1
        assert result["final_position"]["holdings"][0]["symbol"] == "AAPL"

        # Metadata
        assert "metadata" in result
        assert result["metadata"]["total_actions"] == 1

    def test_results_filtering_by_date(self, client, db):
        """Test filtering results by date."""
        response = client.get("/results?start_date=2025-01-15&end_date=2025-01-15")

        results = response.json()["results"]
        assert all(r["date"] == "2025-01-15" for r in results)

    def test_results_filtering_by_model(self, client, db):
        """Test filtering results by model."""
        response = client.get("/results?model=gpt-4&start_date=2025-01-15&end_date=2025-01-15")

        results = response.json()["results"]
        assert all(r["model"] == "gpt-4" for r in results)
