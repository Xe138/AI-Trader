"""
Tool interceptor for injecting runtime context into MCP tool calls.

This interceptor automatically injects `signature` and `today_date` parameters
into buy/sell tool calls to support concurrent multi-model simulations.

It also maintains in-memory position state to track cumulative changes within
a single trading session, ensuring sell proceeds are immediately available for
subsequent buy orders.
"""

from typing import Any, Callable, Awaitable, Dict, Optional


class ContextInjector:
    """
    Intercepts tool calls to inject runtime context (signature, today_date).

    Also maintains cumulative position state during trading session to ensure
    sell proceeds are immediately available for subsequent buys.

    Usage:
        interceptor = ContextInjector(signature="gpt-5", today_date="2025-10-01")
        client = MultiServerMCPClient(config, tool_interceptors=[interceptor])
    """

    def __init__(self, signature: str, today_date: str, job_id: str = None,
                 session_id: int = None, trading_day_id: int = None):
        """
        Initialize context injector.

        Args:
            signature: Model signature to inject
            today_date: Trading date to inject
            job_id: Job UUID to inject (optional)
            session_id: Trading session ID to inject (optional, DEPRECATED)
            trading_day_id: Trading day ID to inject (optional)
        """
        self.signature = signature
        self.today_date = today_date
        self.job_id = job_id
        self.session_id = session_id  # Deprecated but kept for compatibility
        self.trading_day_id = trading_day_id
        self._current_position: Optional[Dict[str, float]] = None

    def reset_position(self) -> None:
        """
        Reset position state (call at start of each trading day).
        """
        self._current_position = None

    async def __call__(
        self,
        request: Any,  # MCPToolCallRequest
        handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:  # MCPToolCallResult
        """
        Intercept tool call and inject context parameters.

        For buy/sell operations, maintains cumulative position state to ensure
        sell proceeds are immediately available for subsequent buys.

        Args:
            request: Tool call request containing name and arguments
            handler: Async callable to execute the actual tool

        Returns:
            Result from handler after injecting context
        """
        # Inject context parameters for trade tools
        if request.name in ["buy", "sell"]:
            # ALWAYS inject/override context parameters (don't trust AI-provided values)
            request.args["signature"] = self.signature
            request.args["today_date"] = self.today_date
            if self.job_id:
                request.args["job_id"] = self.job_id
            if self.session_id:
                request.args["session_id"] = self.session_id
            if self.trading_day_id:
                request.args["trading_day_id"] = self.trading_day_id

            # Inject current position if we're tracking it
            if self._current_position is not None:
                request.args["_current_position"] = self._current_position

        # Call the actual tool handler
        result = await handler(request)

        # Update position state after successful trade
        if request.name in ["buy", "sell"]:
            # Check if result is a valid position dict (not an error)
            if isinstance(result, dict) and "error" not in result and "CASH" in result:
                # Update our tracked position with the new state
                self._current_position = result.copy()

        return result
