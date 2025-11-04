import pytest
from agent.pnl_calculator import DailyPnLCalculator


class TestDailyPnLCalculator:

    def test_first_day_zero_pnl(self):
        """First trading day should have zero P&L."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        result = calculator.calculate(
            previous_day=None,
            current_date="2025-01-15",
            current_prices={"AAPL": 150.0}
        )

        assert result["daily_profit"] == 0.0
        assert result["daily_return_pct"] == 0.0
        assert result["starting_portfolio_value"] == 10000.0
        assert result["days_since_last_trading"] == 0

    def test_positive_pnl_from_price_increase(self):
        """Portfolio gains value when holdings appreciate."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        # Previous day: 10 shares of AAPL at $100, cash $9000
        previous_day = {
            "date": "2025-01-15",
            "ending_cash": 9000.0,
            "ending_portfolio_value": 10000.0,  # 10 * $100 + $9000
            "holdings": [{"symbol": "AAPL", "quantity": 10}]
        }

        # Current day: AAPL now $150
        current_prices = {"AAPL": 150.0}

        result = calculator.calculate(
            previous_day=previous_day,
            current_date="2025-01-16",
            current_prices=current_prices
        )

        # New value: 10 * $150 + $9000 = $10,500
        # Profit: $10,500 - $10,000 = $500
        assert result["daily_profit"] == 500.0
        assert result["daily_return_pct"] == 5.0
        assert result["starting_portfolio_value"] == 10500.0
        assert result["days_since_last_trading"] == 1

    def test_negative_pnl_from_price_decrease(self):
        """Portfolio loses value when holdings depreciate."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        previous_day = {
            "date": "2025-01-15",
            "ending_cash": 9000.0,
            "ending_portfolio_value": 10000.0,
            "holdings": [{"symbol": "AAPL", "quantity": 10}]
        }

        # AAPL drops from $100 to $80
        current_prices = {"AAPL": 80.0}

        result = calculator.calculate(
            previous_day=previous_day,
            current_date="2025-01-16",
            current_prices=current_prices
        )

        # New value: 10 * $80 + $9000 = $9,800
        # Loss: $9,800 - $10,000 = -$200
        assert result["daily_profit"] == -200.0
        assert result["daily_return_pct"] == -2.0

    def test_weekend_gap_calculation(self):
        """Calculate P&L correctly across weekend."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        # Friday
        previous_day = {
            "date": "2025-01-17",  # Friday
            "ending_cash": 9000.0,
            "ending_portfolio_value": 10000.0,
            "holdings": [{"symbol": "AAPL", "quantity": 10}]
        }

        # Monday (3 days later)
        current_prices = {"AAPL": 120.0}

        result = calculator.calculate(
            previous_day=previous_day,
            current_date="2025-01-20",  # Monday
            current_prices=current_prices
        )

        # New value: 10 * $120 + $9000 = $10,200
        assert result["daily_profit"] == 200.0
        assert result["days_since_last_trading"] == 3

    def test_multiple_holdings(self):
        """Calculate P&L with multiple stock positions."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        previous_day = {
            "date": "2025-01-15",
            "ending_cash": 8000.0,
            "ending_portfolio_value": 10000.0,
            "holdings": [
                {"symbol": "AAPL", "quantity": 10},  # Was $100
                {"symbol": "MSFT", "quantity": 5}    # Was $200
            ]
        }

        # Prices change
        current_prices = {
            "AAPL": 110.0,  # +$10
            "MSFT": 190.0   # -$10
        }

        result = calculator.calculate(
            previous_day=previous_day,
            current_date="2025-01-16",
            current_prices=current_prices
        )

        # AAPL: 10 * $110 = $1,100 (was $1,000, +$100)
        # MSFT: 5 * $190 = $950 (was $1,000, -$50)
        # Cash: $8,000 (unchanged)
        # New total: $10,050
        # Profit: $50
        assert result["daily_profit"] == 50.0

    def test_missing_price_raises_error(self):
        """Raise error if price data missing for holding."""
        calculator = DailyPnLCalculator(initial_cash=10000.0)

        previous_day = {
            "date": "2025-01-15",
            "ending_cash": 9000.0,
            "ending_portfolio_value": 10000.0,
            "holdings": [{"symbol": "AAPL", "quantity": 10}]
        }

        # Missing AAPL price
        current_prices = {"MSFT": 150.0}

        with pytest.raises(ValueError, match="Missing price data for AAPL"):
            calculator.calculate(
                previous_day=previous_day,
                current_date="2025-01-16",
                current_prices=current_prices
            )
