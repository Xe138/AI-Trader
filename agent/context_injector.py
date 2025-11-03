"""
Tool interceptor for injecting runtime context into MCP tool calls.

This interceptor automatically injects `signature` and `today_date` parameters
into buy/sell tool calls to support concurrent multi-model simulations.
"""

from typing import Any, Dict


class ContextInjector:
    """
    Intercepts tool calls to inject runtime context (signature, today_date).

    Usage:
        interceptor = ContextInjector(signature="gpt-5", today_date="2025-10-01")
        client = MultiServerMCPClient(config, tool_interceptors=[interceptor])
    """

    def __init__(self, signature: str, today_date: str):
        """
        Initialize context injector.

        Args:
            signature: Model signature to inject
            today_date: Trading date to inject
        """
        self.signature = signature
        self.today_date = today_date

    def __call__(self, tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intercept tool call and inject context parameters.

        Args:
            tool_name: Name of the tool being called
            tool_input: Original tool input parameters

        Returns:
            Modified tool input with injected context
        """
        # Only inject for trade tools (buy/sell)
        if tool_name in ["buy", "sell"]:
            # Inject signature and today_date if not already provided
            if "signature" not in tool_input:
                tool_input["signature"] = self.signature
            if "today_date" not in tool_input:
                tool_input["today_date"] = self.today_date

        return tool_input
