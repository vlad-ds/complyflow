"""
Tests for token counting utilities.
"""

import pytest

from utils.tokens import count_tokens_openai


class TestCountTokensOpenAI:
    """Tests for OpenAI token counting (uses tiktoken locally)."""

    def test_empty_string(self):
        """Empty string should return 0 tokens."""
        assert count_tokens_openai("") == 0

    def test_simple_text(self):
        """Simple English text tokenization."""
        text = "Hello, world!"
        tokens = count_tokens_openai(text)
        assert tokens > 0
        assert tokens < 10  # Short text should be few tokens

    def test_longer_text(self):
        """Longer text should have more tokens."""
        short = "Hello"
        long = "Hello, this is a much longer sentence with many more words."

        short_tokens = count_tokens_openai(short)
        long_tokens = count_tokens_openai(long)

        assert long_tokens > short_tokens

    def test_special_characters(self):
        """Special characters and unicode should be handled."""
        text = "Legal contract between Party A (the 'Licensor') and Party B"
        tokens = count_tokens_openai(text)
        assert tokens > 0

    def test_multiline_text(self):
        """Multiline text should be tokenized."""
        text = """AGREEMENT

        This Agreement is entered into as of January 1, 2024.

        PARTIES:
        1. Company A
        2. Company B
        """
        tokens = count_tokens_openai(text)
        assert tokens > 10  # Reasonable amount for this text
