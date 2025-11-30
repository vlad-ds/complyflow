#!/usr/bin/env python
"""Run extraction, generate reports, judge accuracy, or create eval pairs.

Usage:
    # Run extractions (idempotent - skips existing)
    python -m evaluation extract --models flash

    # Generate comparison report (queries Langfuse for costs)
    python -m evaluation report --models flash

    # Create eval pairs (after all extractions are done)
    python -m evaluation pairs

    # Judge extraction accuracy using LLM-as-judge
    python -m evaluation judge --eval-pairs output/eval_pairs/train_eval_pairs_xxx.json

    # Force re-extraction
    python -m evaluation extract --models flash --force

    # Run all models
    python -m evaluation extract
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.config import EVAL_MODELS, EVAL_PAIRS_DIR, ModelConfig
from evaluation.runner import run_extractions
from evaluation.report import save_comparison_report, save_eval_pairs
from evaluation.judge import (
    judge_eval_pairs,
    export_results_to_csv,
    fetch_langfuse_cost,
    create_judge_summary,
)


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


def cmd_pairs(args):
    """Create eval pairs from existing extractions."""
    models = parse_models(args.models)
    print(f"Creating eval pairs for {args.split} split")

    save_eval_pairs(args.split, models)


def cmd_judge(args):
    """Judge extraction accuracy using LLM-as-judge."""
    import json
    from datetime import datetime
    from evaluation.judge import EVAL_FIELDS

    # Find eval pairs file
    if args.eval_pairs:
        eval_pairs_path = Path(args.eval_pairs)
    else:
        # Find most recent eval pairs file for the split
        pattern = f"{args.split}_eval_pairs_*.json"
        files = sorted(EVAL_PAIRS_DIR.glob(pattern), reverse=True)
        if not files:
            print(f"Error: No eval pairs found for split '{args.split}'")
            print(f"Run 'python -m evaluation pairs --split {args.split}' first")
            sys.exit(1)
        eval_pairs_path = files[0]

    if not eval_pairs_path.exists():
        print(f"Error: Eval pairs file not found: {eval_pairs_path}")
        sys.exit(1)

    print(f"Loading eval pairs from: {eval_pairs_path}")
    with open(eval_pairs_path) as f:
        data = json.load(f)

    eval_pairs = data["eval_pairs"]
    models = args.models.split(",") if args.models else None

    # Handle field exclusion
    fields = EVAL_FIELDS.copy()
    excluded_fields = []
    if args.exclude_fields:
        excluded_fields = [f.strip() for f in args.exclude_fields.split(",")]
        fields = [f for f in fields if f not in excluded_fields]

    print(f"Judging {len(eval_pairs)} contracts")
    if models:
        print(f"Models: {models}")
    if excluded_fields:
        print(f"Excluded fields: {excluded_fields}")
    print(f"Evaluating fields: {fields}")
    print("=" * 80)

    # Run judgments
    results = judge_eval_pairs(eval_pairs, models=models, fields=fields)

    eval_id = results.get("eval_id", "unknown")
    duration = results.get("duration_seconds", 0)
    llm_calls = results.get("llm_calls", 0)

    # Print run info
    print(f"\nEval ID: {eval_id}")
    print(f"Duration: {duration:.1f}s")
    print(f"LLM judge calls: {llm_calls}")

    # Print overall metrics
    overall = results.get("overall_stats", {})
    print("\n" + "=" * 60)
    print("OVERALL METRICS")
    print("=" * 60)
    print(f"Total: {overall.get('total', 0)} | Match: {overall.get('match', 0)} | No Match: {overall.get('no_match', 0)} | Error: {overall.get('error', 0)}")
    print(f"Accuracy: {overall.get('accuracy', 0):.1%}")

    # Print model metrics
    print("\n" + "=" * 60)
    print("MODEL METRICS")
    print("=" * 60)
    print(f"{'Model':<15} {'Match':<8} {'NoMatch':<10} {'Error':<8} {'Accuracy':<10}")
    print("-" * 60)
    for model, stats in sorted(results["model_stats"].items()):
        print(f"{model:<15} {stats['match']:<8} {stats['no_match']:<10} {stats['error']:<8} {stats.get('accuracy', 0):.1%}")

    # Print field metrics
    print("\n" + "=" * 60)
    print("FIELD METRICS")
    print("=" * 60)
    print(f"{'Field':<20} {'Match':<8} {'NoMatch':<10} {'Error':<8} {'Accuracy':<10}")
    print("-" * 60)
    for field, stats in results["field_stats"].items():
        print(f"{field:<20} {stats['match']:<8} {stats['no_match']:<10} {stats['error']:<8} {stats.get('accuracy', 0):.1%}")

    # Fetch Langfuse cost metrics (optional)
    langfuse_metrics = None
    if not args.no_langfuse:
        print("\n" + "=" * 80)
        print("FETCHING LANGFUSE COST METRICS")
        print("=" * 80)
        langfuse_metrics = fetch_langfuse_cost(eval_id, wait_seconds=5)
        if langfuse_metrics.get("trace_count", 0) > 0:
            print(f"Traces: {langfuse_metrics['trace_count']}")
            print(f"Input tokens: {langfuse_metrics['total_input_tokens']:,}")
            print(f"Output tokens: {langfuse_metrics['total_output_tokens']:,}")
            print(f"Total cost: ${langfuse_metrics['total_cost_usd']:.4f}")
        else:
            print(f"Note: {langfuse_metrics.get('note', 'No traces found')}")

    # Save outputs
    output_dir = EVAL_PAIRS_DIR.parent / "judge_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save detailed results JSON
    details_path = output_dir / f"judge_{args.split}_{timestamp}_details.json"
    with open(details_path, "w") as f:
        json.dump({
            "eval_pairs_file": str(eval_pairs_path),
            "generated_at": datetime.now().isoformat(),
            **results,
        }, f, indent=2)

    # Save summary JSON
    summary = create_judge_summary(results, str(eval_pairs_path), langfuse_metrics)
    summary_path = output_dir / f"judge_{args.split}_{timestamp}_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Save CSV for human review
    csv_path = output_dir / f"judge_{args.split}_{timestamp}.csv"
    export_results_to_csv(results, csv_path)

    print("\n" + "=" * 80)
    print("OUTPUT FILES")
    print("=" * 80)
    print(f"Summary:  {summary_path}")
    print(f"Details:  {details_path}")
    print(f"CSV:      {csv_path}")


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

    # Pairs command
    pairs_parser = subparsers.add_parser(
        "pairs",
        parents=[common],
        help="Create eval pairs from existing extractions",
    )
    pairs_parser.set_defaults(func=cmd_pairs)

    # Judge command
    judge_parser = subparsers.add_parser(
        "judge",
        parents=[common],
        help="Judge extraction accuracy using LLM-as-judge",
    )
    judge_parser.add_argument(
        "--eval-pairs",
        type=str,
        default=None,
        help="Path to eval pairs JSON (default: most recent for split)",
    )
    judge_parser.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Skip Langfuse cost metrics (faster)",
    )
    judge_parser.add_argument(
        "--exclude-fields",
        type=str,
        default=None,
        help="Comma-separated fields to exclude from evaluation (e.g., 'effective_date')",
    )
    judge_parser.set_defaults(func=cmd_judge)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
