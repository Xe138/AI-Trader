"""
Tool interceptor for injecting runtime context into MCP tool calls.

This interceptor automatically injects `signature` and `today_date` parameters
into buy/sell tool calls to support concurrent multi-model simulations.
"""

from typing import Any, Callable, Awaitable


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

    async def __call__(
        self,
        request: Any,  # MCPToolCallRequest
        handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:  # MCPToolCallResult
        """
        Intercept tool call and inject context parameters.

        Args:
            request: Tool call request containing name and arguments
            handler: Async callable to execute the actual tool

        Returns:
            Result from handler after injecting context
        """
        # Inject signature and today_date for trade tools
        if request.name in ["buy", "sell"]:
            # Add signature and today_date to args if not present
            if "signature" not in request.args:
                request.args["signature"] = self.signature
            if "today_date" not in request.args:
                request.args["today_date"] = self.today_date

            # Debug logging
            print(f"[ContextInjector] Tool: {request.name}, Args after injection: {request.args}")

        # Call the actual tool handler
        return await handler(request)
