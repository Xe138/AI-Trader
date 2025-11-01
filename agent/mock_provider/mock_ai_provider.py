"""
Mock AI Provider for Development Mode

Returns static but rotating trading responses to test orchestration without AI API costs.
Rotates through NASDAQ 100 stocks in a predictable pattern.
"""

from typing import Optional
from datetime import datetime


class MockAIProvider:
    """Mock AI provider that returns pre-defined trading responses"""

    # Rotation of stocks for variety in testing
    STOCK_ROTATION = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
        "META", "TSLA", "BRK.B", "UNH", "JNJ"
    ]

    def __init__(self):
        """Initialize mock provider"""
        pass

    def generate_response(self, date: str, step: int = 0) -> str:
        """
        Generate mock trading response based on date

        Args:
            date: Trading date (YYYY-MM-DD)
            step: Current step in reasoning loop (0-indexed)

        Returns:
            Mock AI response string with tool calls and finish signal
        """
        # Use date to deterministically select stock
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        day_offset = (date_obj - datetime(2025, 1, 1)).days
        stock_idx = day_offset % len(self.STOCK_ROTATION)
        selected_stock = self.STOCK_ROTATION[stock_idx]

        # Generate mock response
        response = f"""Let me analyze the market for today ({date}).

I'll check the current price for {selected_stock}.
[calls tool_get_price with symbol={selected_stock}]

Based on the analysis, I'll make a small purchase to test the system.
[calls tool_trade with action=buy, symbol={selected_stock}, amount=5]

I've completed today's trading session.
<FINISH_SIGNAL>"""

        return response

    def __str__(self):
        return "MockAIProvider(mode=development)"

    def __repr__(self):
        return self.__str__()
