"""OpenAI GPT provider with structured output support.

Uses the OpenAI API's json_schema response format for reliable JSON extraction.

Requires environment variables:
- OPENAI_API_KEY: Your OpenAI API key
- LANGFUSE_PUBLIC_KEY: Your Langfuse public key (for tracing)
- LANGFUSE_SECRET_KEY: Your Langfuse secret key (for tracing)
"""

# Load .env BEFORE importing langfuse (it reads env vars at import time)
from dotenv import load_dotenv
load_dotenv()

import json
import time
from dataclasses import dataclass
from typing import Any

from langfuse import get_client, observe
from openai import OpenAI
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

from extraction.schema import DateComputationResult
from llm.base import BaseLLMProvider, LLMResponse


@dataclass
class DateComputationResponse:
    """Response from date computation."""

    content: dict  # The computed dates
    model: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    code_interpreter_used: bool
    raw_response: Any = None

# Initialize instrumentation once at module load
_instrumentor = OpenAIInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument()


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider for structured JSON extraction."""

    provider_name = "openai"

    # Available models (as of Nov 2025)
    MODELS = {
        # GPT-5 series (Aug 2025)
        "gpt-5": "gpt-5-2025-08-07",
        "gpt-5-mini": "gpt-5-mini-2025-08-07",
        "gpt-5-nano": "gpt-5-nano-2025-08-07",
        # GPT-5.1 series (Nov 2025)
        "gpt-5.1": "gpt-5.1-2025-11-13",
        # Legacy models
        "gpt-4o": "gpt-4o-2024-08-06",
        "gpt-4o-mini": "gpt-4o-mini-2024-07-18",
    }

    def __init__(self, model: str | None = None):
        """Initialize OpenAI provider.

        Args:
            model: Model to use. Can be a short name ("gpt-5", "gpt-5-mini", etc.)
                   or full model ID. Defaults to "gpt-5".
        """
        self._client = OpenAI()
        self._model = self._resolve_model(model or "gpt-5")

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
        tags: list[str] | None = None,
    ) -> LLMResponse:
        """Extract structured JSON using OpenAI's structured output.

        Args:
            prompt: The extraction prompt/instructions.
            document: The document text to extract from.
            json_schema: JSON schema defining the expected output structure.
            model: Optional model override.
            tags: Optional Langfuse tags for tracking.

        Returns:
            LLMResponse with the JSON string and usage metadata.
        """
        model = self._resolve_model(model) if model else self._model

        # Update Langfuse trace with tags if provided
        if tags:
            langfuse = get_client()
            base_tags = ["extraction", f"provider:{self.provider_name}"]
            all_tags = base_tags + tags
            langfuse.update_current_trace(
                name="openai-extraction",
                tags=all_tags,
                metadata={"model": model, "provider": self.provider_name},
            )

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

    @observe(name="date-computation-standard")
    def compute_dates(
        self,
        prompt: str,
        contract_data: dict,
        tags: list[str] | None = None,
        model: str | None = None,
    ) -> DateComputationResponse:
        """Compute dates using standard chat completion (no code interpreter).

        Args:
            prompt: The date computation prompt template.
            contract_data: Dict with agreement_date, effective_date, expiration_date fields.
            tags: Optional Langfuse tags for tracking.
            model: Optional model override.

        Returns:
            DateComputationResponse with computed dates and usage metadata.
        """
        start_time = time.time()
        model = self._resolve_model(model) if model else self._model

        # Update Langfuse trace with tags
        langfuse = get_client()
        base_tags = ["date-computation", "code-interpreter:false"]
        all_tags = base_tags + (tags or [])
        langfuse.update_current_trace(
            name="date-computation-standard",
            tags=all_tags,
            metadata={
                "model": model,
                "provider": self.provider_name,
                "code_interpreter": False,
            },
        )

        # Format the prompt with contract data
        contract_data_str = json.dumps(contract_data, indent=2)
        full_prompt = prompt.format(contract_data=contract_data_str)

        # Get JSON schema from Pydantic model
        date_schema = DateComputationResult.model_json_schema()

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
                    "name": "date_computation_response",
                    "strict": True,
                    "schema": date_schema,
                },
            },
        )

        latency = time.time() - start_time
        computed_dates = json.loads(response.choices[0].message.content)

        return DateComputationResponse(
            content=computed_dates,
            model=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            latency_seconds=latency,
            code_interpreter_used=False,
            raw_response=response,
        )
