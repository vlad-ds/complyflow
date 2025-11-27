"""Report generator - aggregates metrics from extraction outputs and Langfuse.

Reads eval_ids from extraction JSONs and queries Langfuse for cost/token metrics.
Generates comprehensive reports for model comparison.
"""

import json
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from langfuse import Langfuse

from evaluation.config import (
    CUAD_TRAIN_METADATA,
    CUAD_TEST_METADATA,
    EVAL_MODELS,
    EVAL_PAIRS_DIR,
    OUTPUT_DIR,
    RUN_SUMMARIES_DIR,
    ModelConfig,
)


def _load_ground_truth(split: str = "train") -> list[dict]:
    """Load CUAD ground truth metadata for a split."""
    metadata_path = CUAD_TRAIN_METADATA if split == "train" else CUAD_TEST_METADATA
    if not metadata_path.exists():
        return []
    with open(metadata_path) as f:
        return json.load(f)


def _get_output_path(model_config: ModelConfig, contract_file: str) -> Path:
    """Get the path to the extraction output JSON for a model/contract."""
    output_dir = OUTPUT_DIR / model_config.output_folder
    output_file = contract_file.replace(".pdf", "_extraction.json")
    return output_dir / output_file


def load_model_extractions(
    model_config: ModelConfig,
    split: str = "train",
) -> list[dict]:
    """Load all extraction JSONs for a model/split.

    Returns:
        List of extraction dicts with their data.
    """
    ground_truth = _load_ground_truth(split)
    extractions = []

    for contract in ground_truth:
        contract_file = contract["file"]
        output_path = _get_output_path(model_config, contract_file)

        if output_path.exists():
            with open(output_path) as f:
                extractions.append(json.load(f))

    return extractions


def get_unique_eval_ids(extractions: list[dict]) -> list[str]:
    """Extract unique eval_ids from a list of extraction dicts."""
    eval_ids = set()
    for ext in extractions:
        if ext.get("eval_id"):
            eval_ids.add(ext["eval_id"])
    return sorted(eval_ids)


def fetch_langfuse_metrics_for_eval_id(
    langfuse: Langfuse,
    eval_id: str,
) -> dict:
    """Fetch metrics from Langfuse for a single eval_id.

    Returns:
        Dict with trace_count, total tokens, total cost, and per-trace details.
    """
    traces_response = langfuse.api.trace.list(limit=100, tags=[eval_id])
    traces = traces_response.data

    if not traces:
        return {
            "eval_id": eval_id,
            "trace_count": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "traces": [],
        }

    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0
    trace_details = []

    for trace in traces:
        # Get observations for this trace (contains generation details)
        observations = langfuse.api.observations.get_many(trace_id=trace.id)

        trace_input = 0
        trace_output = 0
        trace_cost = 0.0

        for obs in observations.data:
            # Get token counts from usage_details
            if hasattr(obs, "usage_details") and obs.usage_details:
                trace_input += obs.usage_details.get("input", 0) or 0
                trace_output += obs.usage_details.get("output", 0) or 0

            # Get cost from cost_details or calculated fields
            if hasattr(obs, "cost_details") and obs.cost_details:
                trace_cost += obs.cost_details.get("total", 0) or 0
            elif hasattr(obs, "calculated_total_cost") and obs.calculated_total_cost:
                trace_cost += obs.calculated_total_cost

        total_input_tokens += trace_input
        total_output_tokens += trace_output
        total_cost += trace_cost

        trace_details.append({
            "trace_id": trace.id,
            "name": trace.name,
            "input_tokens": trace_input,
            "output_tokens": trace_output,
            "cost_usd": trace_cost,
        })

    return {
        "eval_id": eval_id,
        "trace_count": len(traces),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": total_cost,
        "traces": trace_details,
    }


def generate_model_report(
    model_config: ModelConfig,
    split: str = "train",
    fetch_langfuse: bool = True,
    wait_seconds: int = 3,
) -> dict:
    """Generate a comprehensive report for a model's extractions.

    Args:
        model_config: Model to report on.
        split: Dataset split.
        fetch_langfuse: Whether to query Langfuse for cost metrics.
        wait_seconds: Seconds to wait before querying Langfuse (for ingestion).

    Returns:
        Report dict with local metrics and Langfuse metrics.
    """
    extractions = load_model_extractions(model_config, split)

    if not extractions:
        return {
            "model": model_config.model,
            "provider": model_config.provider,
            "split": split,
            "contract_count": 0,
            "error": "No extractions found",
        }

    # Aggregate local metrics from extraction JSONs
    total_input_tokens = 0
    total_output_tokens = 0
    total_latency = 0.0

    for ext in extractions:
        usage = ext.get("usage", {})
        total_input_tokens += usage.get("input_tokens") or 0
        total_output_tokens += usage.get("output_tokens") or 0
        total_latency += ext.get("latency_seconds") or 0

    contract_count = len(extractions)

    report = {
        "model": model_config.model,
        "provider": model_config.provider,
        "split": split,
        "generated_at": datetime.now().isoformat(),
        "contract_count": contract_count,
        "local_metrics": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_latency_seconds": total_latency,
            "avg_input_tokens": total_input_tokens / contract_count,
            "avg_output_tokens": total_output_tokens / contract_count,
            "avg_latency_seconds": total_latency / contract_count,
        },
    }

    # Fetch Langfuse metrics if requested
    if fetch_langfuse:
        eval_ids = get_unique_eval_ids(extractions)
        print(f"  Found {len(eval_ids)} unique eval_id(s) for {model_config.model}")

        if eval_ids and wait_seconds > 0:
            print(f"  Waiting {wait_seconds}s for Langfuse ingestion...")
            time.sleep(wait_seconds)

        langfuse = Langfuse()
        langfuse_total_input = 0
        langfuse_total_output = 0
        langfuse_total_cost = 0.0
        langfuse_trace_count = 0
        eval_id_metrics = []

        for eval_id in eval_ids:
            print(f"  Fetching Langfuse metrics for {eval_id}...")
            metrics = fetch_langfuse_metrics_for_eval_id(langfuse, eval_id)
            eval_id_metrics.append(metrics)

            langfuse_total_input += metrics["total_input_tokens"]
            langfuse_total_output += metrics["total_output_tokens"]
            langfuse_total_cost += metrics["total_cost_usd"]
            langfuse_trace_count += metrics["trace_count"]

        report["langfuse_metrics"] = {
            "eval_ids": eval_ids,
            "trace_count": langfuse_trace_count,
            "total_input_tokens": langfuse_total_input,
            "total_output_tokens": langfuse_total_output,
            "total_cost_usd": langfuse_total_cost,
            "avg_cost_per_contract": langfuse_total_cost / contract_count if contract_count else 0,
            "by_eval_id": eval_id_metrics,
        }

    return report


def generate_comparison_report(
    models: list[ModelConfig] | None = None,
    split: str = "train",
    fetch_langfuse: bool = True,
) -> dict:
    """Generate a comparison report across multiple models.

    Args:
        models: Models to compare. Defaults to EVAL_MODELS.
        split: Dataset split.
        fetch_langfuse: Whether to query Langfuse for cost metrics.

    Returns:
        Comparison report with per-model summaries.
    """
    models = models or EVAL_MODELS

    print(f"Generating comparison report for {len(models)} models...")
    print("=" * 60)

    model_reports = []
    for model_config in models:
        print(f"\n{model_config.model}:")
        report = generate_model_report(model_config, split, fetch_langfuse)
        model_reports.append(report)

    # Build comparison summary
    comparison = {
        "generated_at": datetime.now().isoformat(),
        "split": split,
        "models": [m.model for m in models],
        "model_reports": model_reports,
        "summary": [],
    }

    # Create summary table data
    for report in model_reports:
        if report.get("contract_count", 0) == 0:
            continue

        summary_row = {
            "model": report["model"],
            "provider": report["provider"],
            "contracts": report["contract_count"],
            "avg_latency_s": report["local_metrics"]["avg_latency_seconds"],
            "avg_input_tokens": report["local_metrics"]["avg_input_tokens"],
            "avg_output_tokens": report["local_metrics"]["avg_output_tokens"],
        }

        if "langfuse_metrics" in report:
            lf = report["langfuse_metrics"]
            summary_row["total_cost_usd"] = lf["total_cost_usd"]
            summary_row["avg_cost_usd"] = lf["avg_cost_per_contract"]

        comparison["summary"].append(summary_row)

    return comparison


def save_comparison_report(
    models: list[ModelConfig] | None = None,
    split: str = "train",
    fetch_langfuse: bool = True,
) -> Path:
    """Generate and save a comparison report.

    Returns:
        Path to the saved report JSON.
    """
    report = generate_comparison_report(models, split, fetch_langfuse)

    RUN_SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = RUN_SUMMARIES_DIR / f"comparison_{split}_{timestamp}.json"

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary table
    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)
    print(f"{'Model':<15} {'Contracts':<10} {'Avg Latency':<12} {'Avg Tokens':<15} {'Cost USD':<12}")
    print("-" * 80)

    for row in report["summary"]:
        tokens = f"{row['avg_input_tokens']:.0f}/{row['avg_output_tokens']:.0f}"
        cost = f"${row.get('total_cost_usd', 0):.4f}" if "total_cost_usd" in row else "N/A"
        print(f"{row['model']:<15} {row['contracts']:<10} {row['avg_latency_s']:<12.2f} {tokens:<15} {cost:<12}")

    print("=" * 80)
    print(f"\nReport saved to: {output_path}")

    return output_path


def create_eval_pairs(
    split: str = "train",
    models: list[ModelConfig] | None = None,
) -> list[dict]:
    """Create evaluation pairs matching model outputs with ground truth.

    Args:
        split: Dataset split ("train" or "test").
        models: List of model configs. Defaults to EVAL_MODELS.

    Returns:
        List of eval pair dicts for accuracy evaluation.
    """
    models = models or EVAL_MODELS
    ground_truth = _load_ground_truth(split)

    if not ground_truth:
        print(f"No ground truth found for split '{split}'")
        return []

    eval_pairs = []

    for contract in ground_truth:
        contract_file = contract["file"]

        # Collect model outputs
        model_outputs = {}
        for model_config in models:
            output_path = _get_output_path(model_config, contract_file)
            if output_path.exists():
                with open(output_path) as f:
                    model_outputs[model_config.model] = json.load(f)

        eval_pair = {
            "contract_file": contract_file,
            "ground_truth": contract,
            "model_outputs": model_outputs,
        }
        eval_pairs.append(eval_pair)

    return eval_pairs


def save_eval_pairs(
    split: str = "train",
    models: list[ModelConfig] | None = None,
) -> Path:
    """Create and save evaluation pairs to JSON file.

    Returns:
        Path to the saved eval pairs JSON.
    """
    models = models or EVAL_MODELS
    eval_pairs = create_eval_pairs(split, models)

    # Wrap in metadata
    output_data = {
        "generated_at": datetime.now().isoformat(),
        "split": split,
        "models": [m.model for m in models],
        "contract_count": len(eval_pairs),
        "eval_pairs": eval_pairs,
    }

    EVAL_PAIRS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = EVAL_PAIRS_DIR / f"{split}_eval_pairs_{timestamp}.json"

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"Saved {len(eval_pairs)} eval pairs to: {output_path}")
    return output_path
