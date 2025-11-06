"""
Model factory for creating provider-specific chat models.

Supports multiple AI providers with native integrations where available:
- DeepSeek: Uses ChatDeepSeek for native tool calling support
- OpenAI: Uses ChatOpenAI
- Others: Fall back to ChatOpenAI (OpenAI-compatible endpoints)
"""

from typing import Any
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek


def create_model(
    basemodel: str,
    api_key: str,
    base_url: str,
    temperature: float,
    timeout: int
) -> Any:
    """
    Create appropriate chat model based on provider.

    Args:
        basemodel: Model identifier (e.g., "deepseek/deepseek-chat", "openai/gpt-4")
        api_key: API key for the provider
        base_url: Base URL for API endpoint
        temperature: Sampling temperature (0-1)
        timeout: Request timeout in seconds

    Returns:
        Provider-specific chat model instance

    Examples:
        >>> model = create_model("deepseek/deepseek-chat", "key", "url", 0.7, 30)
        >>> isinstance(model, ChatDeepSeek)
        True

        >>> model = create_model("openai/gpt-4", "key", "url", 0.7, 30)
        >>> isinstance(model, ChatOpenAI)
        True
    """
    # Extract provider from basemodel (format: "provider/model-name")
    provider = basemodel.split("/")[0].lower() if "/" in basemodel else "unknown"

    if provider == "deepseek":
        # Use native ChatDeepSeek for DeepSeek models
        # Extract model name without provider prefix
        model_name = basemodel.split("/", 1)[1] if "/" in basemodel else basemodel

        return ChatDeepSeek(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            timeout=timeout
        )
    else:
        # Use ChatOpenAI for OpenAI and OpenAI-compatible endpoints
        # (Anthropic, Google, Qwen, etc. via compatibility layer)
        return ChatOpenAI(
            model=basemodel,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            timeout=timeout
        )
