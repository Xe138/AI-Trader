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

    def __init__(self, signature: str, today_date: str, job_id: str = None, session_id: int = None):
        """
        Initialize context injector.

        Args:
            signature: Model signature to inject
            today_date: Trading date to inject
            job_id: Job UUID to inject (optional)
            session_id: Trading session ID to inject (optional, updated during execution)
        """
        self.signature = signature
        self.today_date = today_date
        self.job_id = job_id
        self.session_id = session_id

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
        # Inject context parameters for trade tools
        if request.name in ["buy", "sell"]:
            # Debug: Log self attributes BEFORE injection
            print(f"[ContextInjector.__call__] ENTRY: id={id(self)}, self.signature={self.signature}, self.today_date={self.today_date}, self.job_id={self.job_id}, self.session_id={self.session_id}")
            print(f"[ContextInjector.__call__] Args BEFORE injection: {request.args}")

            # ALWAYS inject/override context parameters (don't trust AI-provided values)
            request.args["signature"] = self.signature
            request.args["today_date"] = self.today_date
            if self.job_id:
                request.args["job_id"] = self.job_id
            if self.session_id:
                request.args["session_id"] = self.session_id

            # Debug logging
            print(f"[ContextInjector] Tool: {request.name}, Args after injection: {request.args}")

        # Call the actual tool handler
        return await handler(request)
