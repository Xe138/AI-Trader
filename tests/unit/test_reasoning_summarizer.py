import pytest
from unittest.mock import AsyncMock, Mock
from agent.reasoning_summarizer import ReasoningSummarizer


class TestReasoningSummarizer:

    @pytest.mark.asyncio
    async def test_generate_summary_success(self):
        """Test successful AI summary generation."""
        # Mock AI model
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = Mock(
            content="Analyzed AAPL earnings. Bought 10 shares based on positive guidance."
        )

        summarizer = ReasoningSummarizer(model=mock_model)

        reasoning_log = [
            {"role": "user", "content": "Analyze market"},
            {"role": "assistant", "content": "Let me check AAPL"},
            {"role": "tool", "name": "search", "content": "AAPL earnings positive"}
        ]

        summary = await summarizer.generate_summary(reasoning_log)

        assert summary == "Analyzed AAPL earnings. Bought 10 shares based on positive guidance."
        mock_model.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_summary_failure_fallback(self):
        """Test fallback summary when AI generation fails."""
        # Mock AI model that raises exception
        mock_model = AsyncMock()
        mock_model.ainvoke.side_effect = Exception("API error")

        summarizer = ReasoningSummarizer(model=mock_model)

        reasoning_log = [
            {"role": "assistant", "content": "Let me search"},
            {"role": "tool", "name": "search", "content": "Results"},
            {"role": "tool", "name": "trade", "content": "Buy AAPL"},
            {"role": "tool", "name": "trade", "content": "Sell MSFT"}
        ]

        summary = await summarizer.generate_summary(reasoning_log)

        # Should return fallback with stats
        assert "2 trades" in summary
        assert "1 market searches" in summary

    @pytest.mark.asyncio
    async def test_format_reasoning_for_summary(self):
        """Test condensing reasoning log for summary prompt."""
        mock_model = AsyncMock()
        summarizer = ReasoningSummarizer(model=mock_model)

        reasoning_log = [
            {"role": "user", "content": "System prompt here"},
            {"role": "assistant", "content": "I will analyze AAPL"},
            {"role": "tool", "name": "search", "content": "AAPL earnings data..."},
            {"role": "assistant", "content": "Based on analysis, buying AAPL"}
        ]

        formatted = summarizer._format_reasoning_for_summary(reasoning_log)

        # Should include key messages
        assert "analyze AAPL" in formatted
        assert "search" in formatted
        assert "buying AAPL" in formatted

    @pytest.mark.asyncio
    async def test_empty_reasoning_log(self):
        """Test handling empty reasoning log."""
        mock_model = AsyncMock()
        summarizer = ReasoningSummarizer(model=mock_model)

        summary = await summarizer.generate_summary([])

        assert summary == "No trading activity recorded."
