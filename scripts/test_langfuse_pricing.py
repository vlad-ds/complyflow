#!/usr/bin/env python3
"""
Test Langfuse pricing for each model provider.

Runs one call per model and checks if Langfuse tracks pricing.

Usage:
    PYTHONPATH=src uv run python scripts/test_langfuse_pricing.py
"""

# Load env first
from dotenv import load_dotenv
load_dotenv()

import os
import time

from langfuse import Langfuse
from openai import OpenAI
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

# Instrument OpenAI
_instrumentor = OpenAIInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument()

# Instrument Google GenAI (new SDK: google.genai)
try:
    from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
    GoogleGenAIInstrumentor().instrument()
    print("Google GenAI instrumentation: OK")
except ImportError as e:
    print(f"Google GenAI instrumentation: MISSING ({e})")

langfuse = Langfuse()

TEST_PROMPT = "What is 2+2? Answer in exactly 3 words."


def test_openai_gpt5_mini():
    """Test GPT-5-mini pricing."""
    print("\n--- Testing GPT-5-mini ---")
    client = OpenAI()
    try:
        response = client.chat.completions.create(
            model="gpt-5-mini-2025-08-07",
            messages=[{"role": "user", "content": TEST_PROMPT}],
            max_completion_tokens=50,
        )
        print(f"Response: {response.choices[0].message.content}")
        print(f"Tokens: {response.usage.prompt_tokens} in, {response.usage.completion_tokens} out")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_openai_gpt51():
    """Test GPT-5.1 pricing."""
    print("\n--- Testing GPT-5.1 ---")
    client = OpenAI()
    try:
        response = client.chat.completions.create(
            model="gpt-5.1-2025-11-13",
            messages=[{"role": "user", "content": TEST_PROMPT}],
            temperature=0,
            max_completion_tokens=50,
        )
        print(f"Response: {response.choices[0].message.content}")
        print(f"Tokens: {response.usage.prompt_tokens} in, {response.usage.completion_tokens} out")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_cohere():
    """Test Cohere Command-R pricing via Langfuse OpenAI wrapper."""
    print("\n--- Testing Cohere Command-R (via OpenAI compatibility) ---")
    # Use Langfuse's OpenAI wrapper with Cohere's compatibility endpoint
    from langfuse.openai import openai
    client = openai.OpenAI(
        api_key=os.getenv("COHERE_API_KEY"),
        base_url="https://api.cohere.ai/compatibility/v1"
    )
    try:
        response = client.chat.completions.create(
            model="command-r-08-2024",
            messages=[{"role": "user", "content": TEST_PROMPT}],
            max_tokens=50,
        )
        print(f"Response: {response.choices[0].message.content}")
        print(f"Tokens: {response.usage.prompt_tokens} in, {response.usage.completion_tokens} out")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_gemini():
    """Test Gemini 2.5 Flash pricing via google.genai SDK (new SDK)."""
    print("\n--- Testing Gemini 2.5 Flash (google.genai SDK) ---")
    from google import genai

    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=TEST_PROMPT,
        )
        print(f"Response: {response.text}")
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            print(f"Tokens: {response.usage_metadata.prompt_token_count} in, {response.usage_metadata.candidates_token_count} out")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    print("=" * 60)
    print("LANGFUSE PRICING TEST")
    print("=" * 60)

    results = {}

    # Test each model
    results["gpt-5-mini"] = test_openai_gpt5_mini()
    time.sleep(1)

    results["gpt-5.1"] = test_openai_gpt51()
    time.sleep(1)

    results["cohere-command-r"] = test_cohere()
    time.sleep(1)

    results["gemini-2.5-flash"] = test_gemini()

    # Flush Langfuse
    print("\n--- Flushing Langfuse ---")
    langfuse.flush()
    time.sleep(2)  # Give Langfuse time to process

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for model, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"  {model}: {status}")

    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("1. Go to Langfuse UI")
    print("2. Look for recent traces (last few minutes)")
    print("3. Check each trace for 'Cost' column")
    print("4. If cost is missing, we need to configure pricing in Langfuse")
    print("\nLangfuse pricing docs: https://langfuse.com/docs/model-usage-and-cost")


if __name__ == "__main__":
    main()
