"""OpenAI GPT provider with structured output support.

Uses the OpenAI API's json_schema response format for reliable JSON extraction.

Requires environment variables:
- OPENAI_API_KEY: Your OpenAI API key
- LANGFUSE_PUBLIC_KEY: Your Langfuse public key (for tracing)
- LANGFUSE_SECRET_KEY: Your Langfuse secret key (for tracing)
"""

from langfuse import observe
from openai import OpenAI

from llm.base import BaseLLMProvider, LLMResponse


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider for structured JSON extraction."""

    provider_name = "openai"

    # Available models (as of Nov 2025)
    # GPT-4.1 series released April 2025
    MODELS = {
        "gpt-4.1": "gpt-4.1-2025-04-14",
        "gpt-4.1-mini": "gpt-4.1-mini-2025-04-14",
        "gpt-4.1-nano": "gpt-4.1-nano-2025-04-14",
        # Legacy models
        "gpt-4o": "gpt-4o-2024-08-06",
        "gpt-4o-mini": "gpt-4o-mini-2024-07-18",
    }

    def __init__(self, model: str | None = None):
        """Initialize OpenAI provider.

        Args:
            model: Model to use. Can be a short name ("gpt-4.1", "gpt-4.1-mini", etc.)
                   or full model ID. Defaults to "gpt-4.1-mini".
        """
        self._client = OpenAI()
        self._model = self._resolve_model(model or "gpt-4.1-mini")

    def _resolve_model(self, model: str) -> str:
        """Resolve short model name to full model ID."""
        return self.MODELS.get(model, model)

    @property
    def default_model(self) -> str:
        return self._model

    @observe(name="openai-extraction")
    def extract_json(
        self,
        prompt: str,
        document: str,
        json_schema: dict,
        model: str | None = None,
    ) -> LLMResponse:
        """Extract structured JSON using OpenAI's structured output.

        Args:
            prompt: The extraction prompt/instructions.
            document: The document text to extract from.
            json_schema: JSON schema defining the expected output structure.
            model: Optional model override.

        Returns:
            LLMResponse with the JSON string and usage metadata.
        """
        model = self._resolve_model(model) if model else self._model

        full_prompt = f"<contract>\n{document}\n</contract>\n\n{prompt}"

        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": full_prompt,
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "extraction_response",
                    "strict": True,
                    "schema": json_schema,
                },
            },
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            raw_response=response,
        )
