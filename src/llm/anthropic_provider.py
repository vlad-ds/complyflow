"""Anthropic Claude provider with structured output support.

Uses the beta structured outputs API for reliable JSON extraction.

Requires environment variables:
- ANTHROPIC_API_KEY: Your Anthropic API key
- LANGFUSE_PUBLIC_KEY: Your Langfuse public key (for tracing)
- LANGFUSE_SECRET_KEY: Your Langfuse secret key (for tracing)
"""

from anthropic import Anthropic
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

from llm.base import BaseLLMProvider, LLMResponse

# Initialize instrumentation once at module load
_instrumentor = AnthropicInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument()


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider for structured JSON extraction."""

    provider_name = "anthropic"

    # Available models (as of Nov 2025)
    MODELS = {
        "sonnet": "claude-sonnet-4-5-20250929",
        "opus": "claude-opus-4-5-20251101",
        "haiku": "claude-haiku-4-5-20251001",
    }

    def __init__(self, model: str | None = None):
        """Initialize Anthropic provider.

        Args:
            model: Model to use. Can be a short name ("sonnet", "opus", "haiku")
                   or full model ID. Defaults to "sonnet".
        """
        self._client = Anthropic()
        self._model = self._resolve_model(model or "sonnet")

    def _resolve_model(self, model: str) -> str:
        """Resolve short model name to full model ID."""
        return self.MODELS.get(model, model)

    @property
    def default_model(self) -> str:
        return self._model

    def extract_json(
        self,
        prompt: str,
        document: str,
        json_schema: dict,
        model: str | None = None,
    ) -> LLMResponse:
        """Extract structured JSON using Anthropic's structured outputs beta.

        Args:
            prompt: The extraction prompt/instructions.
            document: The document text to extract from.
            json_schema: JSON schema defining the expected output structure.
            model: Optional model override.

        Returns:
            LLMResponse with the JSON string and usage metadata.
        """
        model = self._resolve_model(model) if model else self._model

        response = self._client.beta.messages.create(
            model=model,
            max_tokens=4096,
            betas=["structured-outputs-2025-11-13"],
            messages=[
                {
                    "role": "user",
                    "content": f"<contract>\n{document}\n</contract>\n\n{prompt}",
                }
            ],
            output_format={
                "type": "json_schema",
                "schema": json_schema,
            },
        )

        return LLMResponse(
            content=response.content[0].text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            raw_response=response,
        )
