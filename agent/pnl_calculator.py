"""Daily P&L calculation logic."""

from datetime import datetime
from typing import Optional, Dict, List


class DailyPnLCalculator:
    """Calculate daily profit/loss for trading portfolios."""

    def __init__(self, initial_cash: float):
        """Initialize calculator.

        Args:
            initial_cash: Starting cash amount for first day
        """
        self.initial_cash = initial_cash

    def calculate(
        self,
        previous_day: Optional[Dict],
        current_date: str,
        current_prices: Dict[str, float]
    ) -> Dict:
        """Calculate daily P&L by valuing holdings at current prices.

        Args:
            previous_day: Previous trading day data with keys:
                - date: str
                - ending_cash: float
                - ending_portfolio_value: float
                - holdings: List[Dict] with symbol and quantity
                None if first trading day
            current_date: Current trading date (YYYY-MM-DD)
            current_prices: Dict mapping symbol to current price

        Returns:
            Dict with keys:
                - daily_profit: float
                - daily_return_pct: float
                - starting_portfolio_value: float
                - days_since_last_trading: int

        Raises:
            ValueError: If price data missing for a holding
        """
        if previous_day is None:
            # First trading day - no P&L
            return {
                "daily_profit": 0.0,
                "daily_return_pct": 0.0,
                "starting_portfolio_value": self.initial_cash,
                "days_since_last_trading": 0
            }

        # Calculate days since last trading
        days_gap = self._calculate_day_gap(
            previous_day["date"],
            current_date
        )

        # Value previous holdings at current prices
        current_value = self._calculate_portfolio_value(
            holdings=previous_day["holdings"],
            prices=current_prices,
            cash=previous_day["ending_cash"]
        )

        # Calculate P&L
        previous_value = previous_day["ending_portfolio_value"]
        daily_profit = current_value - previous_value
        daily_return_pct = (daily_profit / previous_value * 100) if previous_value > 0 else 0.0

        return {
            "daily_profit": daily_profit,
            "daily_return_pct": daily_return_pct,
            "starting_portfolio_value": current_value,
            "days_since_last_trading": days_gap
        }

    def _calculate_portfolio_value(
        self,
        holdings: List[Dict],
        prices: Dict[str, float],
        cash: float
    ) -> float:
        """Calculate total portfolio value.

        Args:
            holdings: List of dicts with symbol and quantity
            prices: Dict mapping symbol to price
            cash: Cash balance

        Returns:
            Total portfolio value

        Raises:
            ValueError: If price missing for a holding
        """
        total_value = cash

        for holding in holdings:
            symbol = holding["symbol"]
            quantity = holding["quantity"]

            if symbol not in prices:
                raise ValueError(f"Missing price data for {symbol}")

            total_value += quantity * prices[symbol]

        return total_value

    def _calculate_day_gap(self, date1: str, date2: str) -> int:
        """Calculate number of days between two dates.

        Args:
            date1: Earlier date (YYYY-MM-DD)
            date2: Later date (YYYY-MM-DD)

        Returns:
            Number of days between dates
        """
        d1 = datetime.strptime(date1, "%Y-%m-%d")
        d2 = datetime.strptime(date2, "%Y-%m-%d")
        return (d2 - d1).days
