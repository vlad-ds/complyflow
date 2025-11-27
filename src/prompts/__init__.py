"""Prompt loading utilities."""

from pathlib import Path


PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt from the prompts directory.

    Args:
        name: Prompt filename without extension (e.g., "extraction_v1")

    Returns:
        The prompt content as a string.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist.
    """
    prompt_path = PROMPTS_DIR / f"{name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    return prompt_path.read_text()
