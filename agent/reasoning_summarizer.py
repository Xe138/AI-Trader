"""AI reasoning summary generation."""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class ReasoningSummarizer:
    """Generate summaries of AI trading session reasoning."""

    def __init__(self, model: Any):
        """Initialize summarizer.

        Args:
            model: LangChain chat model for generating summaries
        """
        self.model = model

    async def generate_summary(self, reasoning_log: List[Dict]) -> str:
        """Generate AI summary of trading session reasoning.

        Args:
            reasoning_log: List of message dicts with role and content

        Returns:
            Summary string (2-3 sentences)
        """
        if not reasoning_log:
            return "No trading activity recorded."

        try:
            # Build condensed version of reasoning log
            log_text = self._format_reasoning_for_summary(reasoning_log)

            summary_prompt = f"""You are reviewing your own trading decisions for the day.
Summarize your trading strategy and key decisions in 2-3 sentences.

Focus on:
- What you analyzed
- Why you made the trades you did
- Your overall strategy for the day

Trading session log:
{log_text}

Provide a concise summary:"""

            response = await self.model.ainvoke([
                {"role": "user", "content": summary_prompt}
            ])

            # Extract content from response
            if hasattr(response, 'content'):
                return response.content
            else:
                return str(response)

        except Exception as e:
            logger.error(f"Failed to generate AI reasoning summary: {e}")
            return self._generate_fallback_summary(reasoning_log)

    def _format_reasoning_for_summary(self, reasoning_log: List[Dict]) -> str:
        """Format reasoning log into concise text for summary prompt.

        Args:
            reasoning_log: List of message dicts

        Returns:
            Formatted text representation
        """
        formatted_parts = []

        for msg in reasoning_log:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "assistant":
                # AI's thoughts
                formatted_parts.append(f"AI: {content[:200]}")
            elif role == "tool":
                # Tool results
                tool_name = msg.get("name", "tool")
                formatted_parts.append(f"{tool_name}: {content[:100]}")

        return "\n".join(formatted_parts)

    def _generate_fallback_summary(self, reasoning_log: List[Dict]) -> str:
        """Generate simple statistical summary without AI.

        Args:
            reasoning_log: List of message dicts

        Returns:
            Fallback summary string
        """
        trade_count = sum(
            1 for msg in reasoning_log
            if msg.get("role") == "tool" and msg.get("name") == "trade"
        )

        search_count = sum(
            1 for msg in reasoning_log
            if msg.get("role") == "tool" and msg.get("name") == "search"
        )

        return (
            f"Executed {trade_count} trades using {search_count} market searches. "
            f"Full reasoning log available."
        )
