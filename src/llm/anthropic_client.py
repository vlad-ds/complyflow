"""Anthropic client with Langfuse observability.

Uses OpenTelemetry instrumentation to automatically trace all API calls
with full observability (latency, tokens, costs).

Requires environment variables:
- ANTHROPIC_API_KEY: Your Anthropic API key
- LANGFUSE_PUBLIC_KEY: Your Langfuse public key
- LANGFUSE_SECRET_KEY: Your Langfuse secret key
- LANGFUSE_BASE_URL: Langfuse host (e.g., https://cloud.langfuse.com)
"""

from anthropic import Anthropic
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

# Initialize instrumentation once at module load
_instrumentor = AnthropicInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument()


def get_anthropic_client() -> Anthropic:
    """Get an Anthropic client with Langfuse observability via OTEL.

    Returns:
        Anthropic client that automatically traces all API calls to Langfuse.
    """
    return Anthropic()
