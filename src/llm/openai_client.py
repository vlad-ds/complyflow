"""OpenAI client with Langfuse observability.

Uses Langfuse's drop-in replacement for the OpenAI SDK to automatically
trace all API calls with full observability (latency, tokens, costs).

Requires environment variables:
- OPENAI_API_KEY: Your OpenAI API key
- LANGFUSE_PUBLIC_KEY: Your Langfuse public key
- LANGFUSE_SECRET_KEY: Your Langfuse secret key
- LANGFUSE_HOST: Langfuse host (e.g., https://cloud.langfuse.com)
"""

from langfuse.openai import OpenAI


def get_openai_client() -> OpenAI:
    """Get an OpenAI client wrapped with Langfuse observability.

    Returns:
        OpenAI client that automatically traces all API calls to Langfuse.
    """
    return OpenAI()
