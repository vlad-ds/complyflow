"""Evaluation configuration - models and paths."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ModelConfig:
    """Configuration for a model used in evaluation."""

    provider: str  # "anthropic", "openai", "gemini"
    model: str     # Short name like "sonnet", "gpt-5", "flash"

    @property
    def output_folder(self) -> str:
        """Folder name for storing outputs (same as model short name)."""
        return self.model


# Models to evaluate
# Note: Haiku 4.5 doesn't support structured outputs yet (coming soon per Anthropic)
EVAL_MODELS: list[ModelConfig] = [
    # Anthropic
    ModelConfig(provider="anthropic", model="sonnet"),
    # ModelConfig(provider="anthropic", model="haiku"),  # No structured output support yet
    # OpenAI
    ModelConfig(provider="openai", model="gpt-5"),
    ModelConfig(provider="openai", model="gpt-5-mini"),
    # Gemini
    ModelConfig(provider="gemini", model="flash"),
]


# Path configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Input paths
CUAD_TRAIN_METADATA = PROJECT_ROOT / "cuad" / "train" / "metadata.json"
CUAD_TEST_METADATA = PROJECT_ROOT / "cuad" / "test" / "metadata.json"
EXTRACTED_TEXT_TRAIN = PROJECT_ROOT / "temp" / "extracted_text" / "train"
EXTRACTED_TEXT_TEST = PROJECT_ROOT / "temp" / "extracted_text" / "test"

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "output"
EVAL_PAIRS_DIR = OUTPUT_DIR / "eval_pairs"
RUN_SUMMARIES_DIR = OUTPUT_DIR / "run_summaries"
