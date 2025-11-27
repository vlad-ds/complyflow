"""Google Gemini provider with structured output support.

Uses the Gemini API's response_json_schema for reliable JSON extraction.

Requires environment variables:
- GOOGLE_API_KEY: Your Google AI API key
- LANGFUSE_PUBLIC_KEY: Your Langfuse public key (for tracing)
- LANGFUSE_SECRET_KEY: Your Langfuse secret key (for tracing)
"""

from google import genai
from langfuse import observe
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

from llm.base import BaseLLMProvider, LLMResponse

# Initialize instrumentation once at module load
GoogleGenAIInstrumentor().instrument()


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider for structured JSON extraction."""

    provider_name = "gemini"

    # Available models
    MODELS = {
        "flash": "gemini-2.5-flash",
        "flash-lite": "gemini-2.5-flash-lite",
        "2.0-flash": "gemini-2.0-flash",
    }

    def __init__(self, model: str | None = None):
        """Initialize Gemini provider.

        Args:
            model: Model to use. Can be a short name ("flash", "flash-lite", "pro")
                   or full model ID. Defaults to "flash".
        """
        self._client = genai.Client()
        self._model = self._resolve_model(model or "flash")

    def _resolve_model(self, model: str) -> str:
        """Resolve short model name to full model ID."""
        return self.MODELS.get(model, model)

    @property
    def default_model(self) -> str:
        return self._model

    @observe(name="gemini-extraction")
    def extract_json(
        self,
        prompt: str,
        document: str,
        json_schema: dict,
        model: str | None = None,
    ) -> LLMResponse:
        """Extract structured JSON using Gemini's structured output.

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

        response = self._client.models.generate_content(
            model=model,
            contents=full_prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": json_schema,
            },
        )

        # Extract usage metadata
        usage = response.usage_metadata
        input_tokens = usage.prompt_token_count if usage else 0
        output_tokens = usage.candidates_token_count if usage else 0

        return LLMResponse(
            content=response.text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw_response=response,
        )
