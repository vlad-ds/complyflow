"""Token counting utilities for different LLM providers."""

import tiktoken


def count_tokens_openai(text: str, model: str = "gpt-5") -> int:
    """Count tokens for OpenAI models using tiktoken (local).

    Args:
        text: The text to count tokens for.
        model: The model name to use for tokenization.

    Returns:
        Number of tokens.
    """
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


def count_tokens_anthropic(text: str, model: str = "claude-sonnet-4-5-20250929") -> int:
    """Count tokens for Anthropic models using the API.

    Note: Requires ANTHROPIC_API_KEY environment variable.

    Args:
        text: The text to count tokens for.
        model: The model name to use for tokenization.

    Returns:
        Number of tokens.
    """
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.count_tokens(
        model=model,
        messages=[{"role": "user", "content": text}],
    )
    return response.input_tokens


def count_tokens_gemini(text: str, model: str = "gemini-3-pro-preview") -> int:
    """Count tokens for Gemini models using the API.

    Note: Requires GOOGLE_API_KEY environment variable.

    Args:
        text: The text to count tokens for.
        model: The model name to use for tokenization.

    Returns:
        Number of tokens.
    """
    from google import genai

    client = genai.Client()
    response = client.models.count_tokens(model=model, contents=text)
    return response.total_tokens
