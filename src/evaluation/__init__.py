"""Evaluation module for contract metadata extraction."""

from evaluation.config import EVAL_MODELS, ModelConfig, RUN_SUMMARIES_DIR
from evaluation.runner import run_extractions, run_model_extraction
from evaluation.report import (
    generate_model_report,
    generate_comparison_report,
    save_comparison_report,
    save_eval_pairs,
)

__all__ = [
    "EVAL_MODELS",
    "ModelConfig",
    "RUN_SUMMARIES_DIR",
    "run_extractions",
    "run_model_extraction",
    "generate_model_report",
    "generate_comparison_report",
    "save_comparison_report",
    "save_eval_pairs",
]
