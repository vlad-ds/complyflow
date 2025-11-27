#!/usr/bin/env python
"""Run extraction and/or generate reports.

Usage:
    # Run extractions (idempotent - skips existing)
    python -m evaluation.run_evaluation extract --models flash

    # Generate comparison report (queries Langfuse for costs)
    python -m evaluation.run_evaluation report --models flash

    # Run both extraction and report
    python -m evaluation.run_evaluation all --models flash

    # Force re-extraction
    python -m evaluation.run_evaluation extract --models flash --force

    # Run all models
    python -m evaluation.run_evaluation extract
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.config import EVAL_MODELS, ModelConfig
from evaluation.runner import run_extractions
from evaluation.report import save_comparison_report, save_eval_pairs


def parse_models(models_str: str | None) -> list[ModelConfig] | None:
    """Parse comma-separated model names into ModelConfig list."""
    if not models_str:
        return None  # Use all models

    model_names = [m.strip() for m in models_str.split(",")]
    model_lookup = {m.model: m for m in EVAL_MODELS}

    selected = []
    for name in model_names:
        if name not in model_lookup:
            available = ", ".join(model_lookup.keys())
            print(f"Error: Unknown model '{name}'. Available: {available}")
            sys.exit(1)
        selected.append(model_lookup[name])

    return selected


def cmd_extract(args):
    """Run extractions."""
    models = parse_models(args.models)
    print(f"Running extractions on {args.split} split")
    if models:
        print(f"Models: {[m.model for m in models]}")
    else:
        print(f"Models: ALL ({[m.model for m in EVAL_MODELS]})")

    run_extractions(models, args.split, args.force)


def cmd_report(args):
    """Generate comparison report."""
    models = parse_models(args.models)
    print(f"Generating report for {args.split} split")

    save_comparison_report(models, args.split, fetch_langfuse=not args.no_langfuse)
    save_eval_pairs(args.split, models)


def cmd_all(args):
    """Run extractions then generate report."""
    cmd_extract(args)
    print("\n" + "=" * 60)
    print("GENERATING REPORT")
    print("=" * 60)
    cmd_report(args)


def main():
    parser = argparse.ArgumentParser(
        description="Run extraction evaluation and generate reports"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Common arguments
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--split",
        type=str,
        default="train",
        choices=["train", "test"],
        help="Dataset split (default: train)",
    )
    common.add_argument(
        "--models",
        type=str,
        default=None,
        help="Comma-separated list of models (default: all)",
    )

    # Extract command
    extract_parser = subparsers.add_parser(
        "extract",
        parents=[common],
        help="Run extractions (idempotent)",
    )
    extract_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-extraction even if outputs exist",
    )
    extract_parser.set_defaults(func=cmd_extract)

    # Report command
    report_parser = subparsers.add_parser(
        "report",
        parents=[common],
        help="Generate comparison report",
    )
    report_parser.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Skip Langfuse metrics (faster, no cost data)",
    )
    report_parser.set_defaults(func=cmd_report)

    # All command (extract + report)
    all_parser = subparsers.add_parser(
        "all",
        parents=[common],
        help="Run extractions then generate report",
    )
    all_parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-extraction",
    )
    all_parser.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Skip Langfuse metrics",
    )
    all_parser.set_defaults(func=cmd_all)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
