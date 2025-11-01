"""
Mock LangChain-compatible chat model for development mode

Wraps MockAIProvider to work with LangChain's agent framework.
"""

from typing import Any, List, Optional, Dict
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from .mock_ai_provider import MockAIProvider


class MockChatModel(BaseChatModel):
    """
    Mock chat model compatible with LangChain's agent framework

    Attributes:
        date: Current trading date for response generation
        step_counter: Tracks reasoning steps within a trading session
        provider: MockAIProvider instance
    """

    date: str = "2025-01-01"
    step_counter: int = 0
    provider: Optional[MockAIProvider] = None

    def __init__(self, date: str = "2025-01-01", **kwargs):
        """
        Initialize mock chat model

        Args:
            date: Trading date for mock responses
            **kwargs: Additional LangChain model parameters
        """
        super().__init__(**kwargs)
        self.date = date
        self.step_counter = 0
        self.provider = MockAIProvider()

    @property
    def _llm_type(self) -> str:
        """Return identifier for this LLM type"""
        return "mock-chat-model"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate mock response (synchronous)

        Args:
            messages: Input messages (ignored in mock)
            stop: Stop sequences (ignored in mock)
            run_manager: LangChain run manager
            **kwargs: Additional generation parameters

        Returns:
            ChatResult with mock AI response
        """
        response_text = self.provider.generate_response(self.date, self.step_counter)
        self.step_counter += 1

        message = AIMessage(
            content=response_text,
            response_metadata={"finish_reason": "stop"}
        )

        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """
        Generate mock response (asynchronous)

        Same as _generate but async-compatible for LangChain agents.
        """
        return self._generate(messages, stop, run_manager, **kwargs)

    def invoke(self, input: Any, **kwargs) -> AIMessage:
        """Synchronous invoke (LangChain compatibility)"""
        if isinstance(input, list):
            messages = input
        else:
            messages = []

        result = self._generate(messages, **kwargs)
        return result.generations[0].message

    async def ainvoke(self, input: Any, **kwargs) -> AIMessage:
        """Asynchronous invoke (LangChain compatibility)"""
        if isinstance(input, list):
            messages = input
        else:
            messages = []

        result = await self._agenerate(messages, **kwargs)
        return result.generations[0].message
