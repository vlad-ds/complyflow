"""Date computation evaluation module.

Runs date computation on contracts and evaluates against ground truth using exact match.
Records metrics to Langfuse and outputs rich JSON evaluation results.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from langfuse import get_client

from extraction.compute_dates import (
    compute_dates_for_extraction,
    get_extraction_files,
)


GROUND_TRUTH_PATH = Path("output/date_computation/ground_truth.json")
EVAL_OUTPUT_DIR = Path("output/date_computation/eval_results")

# Date fields to evaluate
DATE_FIELDS = [
    "agreement_date",
    "effective_date",
    "expiration_date",
    "notice_deadline",
    "first_renewal_date",
]


@dataclass
class FieldResult:
    """Result for a single field comparison."""

    field: str
    expected: dict | str | None
    actual: dict | str | None
    match: bool


@dataclass
class ContractResult:
    """Evaluation result for a single contract."""

    contract_id: str
    split: str
    fields: list[FieldResult]
    fields_correct: int
    fields_total: int
    accuracy: float
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    model: str


@dataclass
class EvalSummary:
    """Summary of the entire evaluation run."""

    eval_id: str
    timestamp: str
    model: str
    split: str
    num_contracts: int
    total_fields: int
    correct_fields: int
    field_accuracy: float
    contracts_perfect: int
    contract_accuracy: float
    total_input_tokens: int
    total_output_tokens: int
    total_latency_seconds: float
    avg_latency_seconds: float
    langfuse_cost_usd: float | None
    contracts: list[ContractResult]
    field_breakdown: dict[str, dict]


def load_ground_truth() -> dict:
    """Load ground truth dataset."""
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


def normalize_date_value(value) -> dict | str | None:
    """Normalize a date value for comparison.

    Handles:
    - Dict with year/month/day
    - Special strings: "perpetual", "conditional"
    - None/null
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.lower() if value else None
    if isinstance(value, dict):
        # Normalize dict to ensure consistent comparison
        if "year" in value:
            return {
                "year": value["year"],
                "month": value["month"],
                "day": value["day"],
            }
        return value
    return value


def compare_field(expected, actual) -> bool:
    """Compare two field values for exact match."""
    norm_expected = normalize_date_value(expected)
    norm_actual = normalize_date_value(actual)
    return norm_expected == norm_actual


def evaluate_contract(
    contract_id: str,
    expected: dict,
    actual: dict,
    split: str,
    input_tokens: int,
    output_tokens: int,
    latency_seconds: float,
    model: str,
) -> ContractResult:
    """Evaluate a single contract's computed dates against ground truth."""
    field_results = []

    for field in DATE_FIELDS:
        exp_val = expected.get(field)
        act_val = actual.get(field)
        match = compare_field(exp_val, act_val)

        field_results.append(
            FieldResult(
                field=field,
                expected=exp_val,
                actual=act_val,
                match=match,
            )
        )

    correct = sum(1 for r in field_results if r.match)
    total = len(field_results)

    return ContractResult(
        contract_id=contract_id,
        split=split,
        fields=field_results,
        fields_correct=correct,
        fields_total=total,
        accuracy=correct / total if total > 0 else 0.0,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_seconds=latency_seconds,
        model=model,
    )


def get_langfuse_cost(eval_id: str) -> float | None:
    """Query Langfuse for total cost of traces with this eval_id tag."""
    try:
        from langfuse_client import get_traces_by_tag

        traces = get_traces_by_tag(eval_id)
        if not traces:
            return None

        total_cost = sum(
            t.get("totalCost", 0) or 0
            for t in traces
        )
        return total_cost
    except Exception as e:
        print(f"Warning: Could not get Langfuse cost: {e}")
        return None


def run_evaluation(
    extractions_dir: Path,
    split: Literal["train", "test", "train_2", "all"] = "all",
    model: str = "gpt-5-mini",
) -> EvalSummary:
    """Run date computation evaluation.

    Args:
        extractions_dir: Directory containing extraction JSON files.
        split: Which data split to evaluate.
        model: Model to use for date computation.

    Returns:
        EvalSummary with detailed results.
    """
    # Load ground truth
    ground_truth = load_ground_truth()
    gt_contracts = ground_truth["contracts"]

    # Generate eval ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    eval_id = f"date_eval_{split}_{timestamp}"

    print(f"Running date computation evaluation")
    print(f"  Eval ID: {eval_id}")
    print(f"  Model: {model}")
    print(f"  Split: {split}")
    print()

    # Get files for split
    files = get_extraction_files(extractions_dir, split)

    # Update Langfuse trace
    langfuse = get_client()
    langfuse.update_current_trace(
        name=eval_id,
        tags=["date-eval", f"split:{split}", eval_id],
        metadata={
            "model": model,
            "split": split,
            "num_contracts": len(files),
        },
    )

    results = []
    for i, extraction_path in enumerate(files, 1):
        # Extract contract ID from filename
        contract_id = extraction_path.stem.replace("_extraction", "")

        # Check if we have ground truth for this contract
        if contract_id not in gt_contracts:
            print(f"  [{i}/{len(files)}] {contract_id}... SKIP (no ground truth)")
            continue

        gt_data = gt_contracts[contract_id]

        # Skip if wrong split
        if split != "all" and gt_data["split"] != split:
            continue

        print(f"  [{i}/{len(files)}] {contract_id}...", end=" ", flush=True)

        try:
            # Run date computation
            result = compute_dates_for_extraction(
                extraction_path,
                use_code_interpreter=False,
                model=model,
                eval_id=eval_id,
                tags=[f"contract:{contract_id}"],
            )

            # Evaluate against ground truth
            contract_result = evaluate_contract(
                contract_id=contract_id,
                expected=gt_data["expected"],
                actual=result.computed_dates,
                split=gt_data["split"],
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_seconds=result.latency_seconds,
                model=result.model,
            )

            results.append(contract_result)

            status = "OK" if contract_result.accuracy == 1.0 else f"{contract_result.accuracy:.0%}"
            print(f"{status} ({contract_result.latency_seconds:.1f}s)")

        except Exception as e:
            print(f"ERROR: {e}")
            continue

    # Calculate summary metrics
    total_fields = sum(r.fields_total for r in results)
    correct_fields = sum(r.fields_correct for r in results)
    perfect_contracts = sum(1 for r in results if r.accuracy == 1.0)

    # Field-level breakdown
    field_breakdown = {}
    for field in DATE_FIELDS:
        field_correct = sum(
            1 for r in results
            for f in r.fields
            if f.field == field and f.match
        )
        field_total = sum(
            1 for r in results
            for f in r.fields
            if f.field == field
        )
        field_breakdown[field] = {
            "correct": field_correct,
            "total": field_total,
            "accuracy": field_correct / field_total if field_total > 0 else 0.0,
        }

    # Get cost from Langfuse
    langfuse_cost = get_langfuse_cost(eval_id)

    summary = EvalSummary(
        eval_id=eval_id,
        timestamp=timestamp,
        model=model,
        split=split,
        num_contracts=len(results),
        total_fields=total_fields,
        correct_fields=correct_fields,
        field_accuracy=correct_fields / total_fields if total_fields > 0 else 0.0,
        contracts_perfect=perfect_contracts,
        contract_accuracy=perfect_contracts / len(results) if results else 0.0,
        total_input_tokens=sum(r.input_tokens for r in results),
        total_output_tokens=sum(r.output_tokens for r in results),
        total_latency_seconds=sum(r.latency_seconds for r in results),
        avg_latency_seconds=(
            sum(r.latency_seconds for r in results) / len(results) if results else 0.0
        ),
        langfuse_cost_usd=langfuse_cost,
        contracts=results,
        field_breakdown=field_breakdown,
    )

    return summary


def save_eval_results(summary: EvalSummary) -> Path:
    """Save evaluation results to JSON file."""
    EVAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_path = EVAL_OUTPUT_DIR / f"{summary.eval_id}.json"

    # Convert to dict, handling nested dataclasses
    def to_dict(obj):
        if hasattr(obj, "__dataclass_fields__"):
            return {k: to_dict(v) for k, v in asdict(obj).items()}
        if isinstance(obj, list):
            return [to_dict(item) for item in obj]
        if isinstance(obj, dict):
            return {k: to_dict(v) for k, v in obj.items()}
        return obj

    result_dict = to_dict(summary)

    with open(output_path, "w") as f:
        json.dump(result_dict, f, indent=2)

    return output_path


def print_summary(summary: EvalSummary):
    """Print evaluation summary to console."""
    print()
    print("=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"Eval ID: {summary.eval_id}")
    print(f"Model: {summary.model}")
    print(f"Split: {summary.split}")
    print()
    print(f"Contracts: {summary.num_contracts}")
    print(f"  Perfect: {summary.contracts_perfect} ({summary.contract_accuracy:.1%})")
    print()
    print(f"Fields: {summary.correct_fields}/{summary.total_fields} ({summary.field_accuracy:.1%})")
    print()
    print("Field Breakdown:")
    for field, stats in summary.field_breakdown.items():
        print(f"  {field}: {stats['correct']}/{stats['total']} ({stats['accuracy']:.1%})")
    print()
    print(f"Tokens: {summary.total_input_tokens} in, {summary.total_output_tokens} out")
    print(f"Latency: {summary.total_latency_seconds:.1f}s total, {summary.avg_latency_seconds:.1f}s avg")
    if summary.langfuse_cost_usd is not None:
        print(f"Cost: ${summary.langfuse_cost_usd:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run date computation evaluation")
    parser.add_argument(
        "--extractions-dir",
        type=Path,
        default=Path("output/gpt-5-mini"),
        help="Directory containing extraction JSON files",
    )
    parser.add_argument(
        "--split",
        choices=["train", "test", "train_2", "all"],
        default="all",
        help="Data split to evaluate",
    )
    parser.add_argument(
        "--model",
        default="gpt-5-mini",
        help="Model to use for date computation",
    )

    args = parser.parse_args()

    # Run evaluation
    summary = run_evaluation(
        extractions_dir=args.extractions_dir,
        split=args.split,
        model=args.model,
    )

    # Save results
    output_path = save_eval_results(summary)

    # Print summary
    print_summary(summary)
    print(f"\nResults saved to: {output_path}")
