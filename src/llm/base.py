"""Base class for LLM providers with structured output support."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str  # The JSON string response
    model: str  # Model identifier used
    input_tokens: int
    output_tokens: int
    raw_response: Any = None  # Original provider response


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    All providers must implement structured JSON output extraction.
    """

    provider_name: str  # e.g., "anthropic", "openai", "gemini"

    @abstractmethod
    def extract_json(
        self,
        prompt: str,
        document: str,
        json_schema: dict,
        model: str | None = None,
    ) -> LLMResponse:
        """Extract structured JSON from a document.

        Args:
            prompt: The extraction prompt/instructions.
            document: The document text to extract from.
            json_schema: JSON schema defining the expected output structure.
            model: Optional model override (uses provider default if None).

        Returns:
            LLMResponse with the JSON string and usage metadata.
        """
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model for this provider."""
        pass

    def get_langfuse_session_name(self, base_name: str = "extraction-eval") -> str:
        """Get Langfuse session name with provider suffix.

        Args:
            base_name: Base session name (default: "extraction-eval").

        Returns:
            Session name like "extraction-eval-anthropic".
        """
        return f"{base_name}-{self.provider_name}"
