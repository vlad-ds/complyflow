"""LLM providers with structured output support and Langfuse observability."""

from llm.base import BaseLLMProvider, LLMResponse
from llm.anthropic_provider import AnthropicProvider
from llm.gemini_provider import GeminiProvider
from llm.openai_provider import OpenAIProvider

# Provider registry for easy lookup
PROVIDERS = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
}


def get_provider(name: str, model: str | None = None) -> BaseLLMProvider:
    """Get an LLM provider by name.

    Args:
        name: Provider name ("anthropic", "gemini", "openai").
        model: Optional model override for the provider.

    Returns:
        Initialized provider instance.

    Raises:
        ValueError: If provider name is not recognized.
    """
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider: {name}. Available: {list(PROVIDERS.keys())}"
        )
    return PROVIDERS[name](model=model)


__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "AnthropicProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "PROVIDERS",
    "get_provider",
]
