"""Date computation module for converting extracted dates to structured date objects.

This module takes extraction results and computes actual date objects from:
- Absolute dates (ISO format) -> direct parsing
- Relative terms (e.g., "5 years from Effective Date") -> computation
- Special cases (perpetual, conditional) -> markers
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from prompts import load_prompt
from llm.openai_provider import OpenAIProvider, DateComputationResponse
from llm.openai_assistants_provider import (
    OpenAIAssistantsProvider,
    DateComputationResponse as AssistantsDateComputationResponse,
)


# Train/test split based on existing evaluation
# Format: filename ends with "{suffix}_extraction.json"
TRAIN_FILES = [
    "01_service_gpaq",
    "02_service_reynolds",
    "03_service_verizon",
    "04_service_integrity",
    "05_license_gopage",
    "06_license_morganstanley",
    "07_license_cytodyn",
    "08_license_artara",
    "09_outsourcing_photronics",
    "10_outsourcing_paratek",
]

TEST_FILES = [
    "01_service_mplx",
    "02_service_martinmidstream",
    "03_service_blackstonegsolo",
    "04_service_atmosenergy",
    "05_license_pacificapentert",
    "06_license_midwestenergyem",
    "07_license_gpaqacquisition",
    "08_license_euromediaholdin",
    "09_outsourcing_sykeshealthplan",
    "10_outsourcing_ofgban",
]


@dataclass
class DateComputationResult:
    """Result of date computation for a single contract."""

    source_file: str
    input_data: dict  # The date fields from extraction
    computed_dates: dict  # The computed date objects
    model: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    code_interpreter_used: bool
    eval_id: str


def get_extraction_files(
    extractions_dir: Path,
    split: Literal["train", "test", "all"] = "train",
) -> list[Path]:
    """Get extraction files for the specified split.

    Args:
        extractions_dir: Directory containing extraction JSON files.
        split: Which split to return ("train", "test", or "all").

    Returns:
        List of extraction file paths.
    """
    all_files = sorted(extractions_dir.glob("*_extraction.json"))

    if split == "all":
        return all_files

    # Use exact file prefix matching
    file_prefixes = TRAIN_FILES if split == "train" else TEST_FILES

    return [
        f
        for f in all_files
        if f.stem.replace("_extraction", "") in file_prefixes
    ]


def extract_date_fields(extraction_path: Path) -> dict:
    """Extract date-related fields from an extraction file.

    Args:
        extraction_path: Path to extraction JSON file.

    Returns:
        Dict with date fields including notice_period and renewal_term for derived calculations.
    """
    with open(extraction_path) as f:
        data = json.load(f)

    extraction = data.get("extraction", {})

    return {
        "agreement_date": {
            "raw_snippet": extraction.get("agreement_date", {}).get("raw_snippet", ""),
            "normalized_value": extraction.get("agreement_date", {}).get(
                "normalized_value", ""
            ),
        },
        "effective_date": {
            "raw_snippet": extraction.get("effective_date", {}).get("raw_snippet", ""),
            "normalized_value": extraction.get("effective_date", {}).get(
                "normalized_value", ""
            ),
        },
        "expiration_date": {
            "raw_snippet": extraction.get("expiration_date", {}).get("raw_snippet", ""),
            "normalized_value": extraction.get("expiration_date", {}).get(
                "normalized_value", ""
            ),
        },
        "notice_period": {
            "raw_snippet": extraction.get("notice_period", {}).get("raw_snippet", ""),
            "normalized_value": extraction.get("notice_period", {}).get(
                "normalized_value", ""
            ),
        },
        "renewal_term": {
            "raw_snippet": extraction.get("renewal_term", {}).get("raw_snippet", ""),
            "normalized_value": extraction.get("renewal_term", {}).get(
                "normalized_value", ""
            ),
        },
    }


def compute_dates_for_extraction(
    extraction_path: Path,
    use_code_interpreter: bool = True,
    model: str = "gpt-5-mini",
    eval_id: str | None = None,
    tags: list[str] | None = None,
) -> DateComputationResult:
    """Compute dates for a single extraction file.

    Args:
        extraction_path: Path to extraction JSON file.
        use_code_interpreter: Whether to use Assistants API with code interpreter.
        model: Model to use.
        eval_id: Optional evaluation ID for Langfuse tracking.
        tags: Optional additional Langfuse tags.

    Returns:
        DateComputationResult with computed dates and metadata.
    """
    # Load prompt
    prompt = load_prompt("date_computation_v1")

    # Extract date fields
    date_fields = extract_date_fields(extraction_path)

    # Build tags
    all_tags = tags or []
    if eval_id:
        all_tags.append(eval_id)

    # Compute dates using appropriate provider
    if use_code_interpreter:
        provider = OpenAIAssistantsProvider(model=model)
        response = provider.compute_dates(prompt, date_fields, tags=all_tags)
    else:
        provider = OpenAIProvider(model=model)
        response = provider.compute_dates(prompt, date_fields, tags=all_tags, model=model)

    return DateComputationResult(
        source_file=extraction_path.name,
        input_data=date_fields,
        computed_dates=response.content,
        model=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_seconds=response.latency_seconds,
        code_interpreter_used=response.code_interpreter_used,
        eval_id=eval_id or "",
    )


def compute_dates_batch(
    extractions_dir: Path,
    output_dir: Path,
    split: Literal["train", "test", "all"] = "train",
    use_code_interpreter: bool = True,
    model: str = "gpt-5-mini",
    eval_id: str | None = None,
) -> list[DateComputationResult]:
    """Compute dates for a batch of extraction files.

    Args:
        extractions_dir: Directory containing extraction JSON files.
        output_dir: Directory to save results.
        split: Which data split to process.
        use_code_interpreter: Whether to use Assistants API with code interpreter.
        model: Model to use.
        eval_id: Optional evaluation ID for Langfuse tracking.

    Returns:
        List of DateComputationResult objects.
    """
    from datetime import datetime

    # Generate eval_id if not provided
    if not eval_id:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ci_tag = "ci" if use_code_interpreter else "std"
        eval_id = f"date_eval_{ci_tag}_{timestamp}"

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    results_dir = output_dir / f"{eval_id}_results"
    results_dir.mkdir(exist_ok=True)

    # Get files for split
    files = get_extraction_files(extractions_dir, split)
    print(f"Processing {len(files)} files from {split} split...")
    print(f"Code interpreter: {use_code_interpreter}")
    print(f"Eval ID: {eval_id}")

    # Build tags for Langfuse
    tags = [f"split:{split}", eval_id]

    results = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_latency = 0.0

    for i, extraction_path in enumerate(files, 1):
        print(f"  [{i}/{len(files)}] {extraction_path.name}...", end=" ", flush=True)

        try:
            result = compute_dates_for_extraction(
                extraction_path,
                use_code_interpreter=use_code_interpreter,
                model=model,
                eval_id=eval_id,
                tags=tags,
            )
            results.append(result)

            # Save individual result
            result_path = results_dir / extraction_path.name.replace(
                "_extraction.json", "_dates.json"
            )
            with open(result_path, "w") as f:
                json.dump(asdict(result), f, indent=2)

            total_input_tokens += result.input_tokens
            total_output_tokens += result.output_tokens
            total_latency += result.latency_seconds

            print(
                f"OK ({result.latency_seconds:.1f}s, "
                f"CI={'yes' if result.code_interpreter_used else 'no'})"
            )

        except Exception as e:
            print(f"ERROR: {e}")
            continue

    # Save summary
    summary = {
        "eval_id": eval_id,
        "split": split,
        "model": model,
        "code_interpreter": use_code_interpreter,
        "num_files": len(files),
        "num_successful": len(results),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_latency_seconds": total_latency,
        "avg_latency_seconds": total_latency / len(results) if results else 0,
        "files": [asdict(r) for r in results],
    }

    summary_path = output_dir / f"{eval_id}_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nSummary saved to: {summary_path}")
    print(f"Total tokens: {total_input_tokens} in, {total_output_tokens} out")
    print(f"Total latency: {total_latency:.1f}s")

    return results


def run_ab_comparison(
    extractions_dir: Path,
    output_dir: Path,
    split: Literal["train", "test"] = "train",
    model: str = "gpt-5-mini",
) -> dict:
    """Run A/B comparison between code interpreter and standard approaches.

    Args:
        extractions_dir: Directory containing extraction JSON files.
        output_dir: Directory to save results.
        split: Which data split to process.
        model: Model to use.

    Returns:
        Comparison summary dict.
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 60)
    print(f"A/B Comparison: {split} split")
    print("=" * 60)

    # Run with code interpreter
    print("\n>>> Running WITH code interpreter...")
    ci_eval_id = f"date_eval_ci_{split}_{timestamp}"
    ci_results = compute_dates_batch(
        extractions_dir,
        output_dir,
        split=split,
        use_code_interpreter=True,
        model=model,
        eval_id=ci_eval_id,
    )

    # Run without code interpreter
    print("\n>>> Running WITHOUT code interpreter...")
    std_eval_id = f"date_eval_std_{split}_{timestamp}"
    std_results = compute_dates_batch(
        extractions_dir,
        output_dir,
        split=split,
        use_code_interpreter=False,
        model=model,
        eval_id=std_eval_id,
    )

    # Compare results
    comparison = {
        "timestamp": timestamp,
        "split": split,
        "model": model,
        "code_interpreter": {
            "eval_id": ci_eval_id,
            "num_files": len(ci_results),
            "total_input_tokens": sum(r.input_tokens for r in ci_results),
            "total_output_tokens": sum(r.output_tokens for r in ci_results),
            "total_latency_seconds": sum(r.latency_seconds for r in ci_results),
            "avg_latency_seconds": (
                sum(r.latency_seconds for r in ci_results) / len(ci_results)
                if ci_results
                else 0
            ),
        },
        "standard": {
            "eval_id": std_eval_id,
            "num_files": len(std_results),
            "total_input_tokens": sum(r.input_tokens for r in std_results),
            "total_output_tokens": sum(r.output_tokens for r in std_results),
            "total_latency_seconds": sum(r.latency_seconds for r in std_results),
            "avg_latency_seconds": (
                sum(r.latency_seconds for r in std_results) / len(std_results)
                if std_results
                else 0
            ),
        },
        "differences": [],
    }

    # Find differences in computed dates
    ci_by_file = {r.source_file: r for r in ci_results}
    std_by_file = {r.source_file: r for r in std_results}

    for filename in ci_by_file:
        if filename in std_by_file:
            ci_dates = ci_by_file[filename].computed_dates
            std_dates = std_by_file[filename].computed_dates

            if ci_dates != std_dates:
                comparison["differences"].append(
                    {
                        "file": filename,
                        "code_interpreter": ci_dates,
                        "standard": std_dates,
                    }
                )

    comparison["num_differences"] = len(comparison["differences"])
    comparison["agreement_rate"] = (
        1 - len(comparison["differences"]) / len(ci_results) if ci_results else 0
    )

    # Save comparison
    comparison_path = output_dir / f"ab_comparison_{split}_{timestamp}.json"
    with open(comparison_path, "w") as f:
        json.dump(comparison, f, indent=2)

    print("\n" + "=" * 60)
    print("A/B COMPARISON RESULTS")
    print("=" * 60)
    print(f"\nCode Interpreter:")
    print(f"  Tokens: {comparison['code_interpreter']['total_input_tokens']} in, "
          f"{comparison['code_interpreter']['total_output_tokens']} out")
    print(f"  Latency: {comparison['code_interpreter']['total_latency_seconds']:.1f}s total, "
          f"{comparison['code_interpreter']['avg_latency_seconds']:.1f}s avg")
    print(f"\nStandard:")
    print(f"  Tokens: {comparison['standard']['total_input_tokens']} in, "
          f"{comparison['standard']['total_output_tokens']} out")
    print(f"  Latency: {comparison['standard']['total_latency_seconds']:.1f}s total, "
          f"{comparison['standard']['avg_latency_seconds']:.1f}s avg")
    print(f"\nDifferences: {comparison['num_differences']} / {len(ci_results)} files")
    print(f"Agreement rate: {comparison['agreement_rate']:.1%}")
    print(f"\nComparison saved to: {comparison_path}")

    return comparison


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compute dates from contract extractions")
    parser.add_argument(
        "--extractions-dir",
        type=Path,
        default=Path("output/dataset/extractions"),
        help="Directory containing extraction JSON files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/date_computation"),
        help="Directory to save results",
    )
    parser.add_argument(
        "--split",
        choices=["train", "test", "all"],
        default="train",
        help="Data split to process",
    )
    parser.add_argument(
        "--model",
        default="gpt-5-mini",
        help="Model to use",
    )
    parser.add_argument(
        "--no-code-interpreter",
        action="store_true",
        help="Disable code interpreter (use standard chat completion)",
    )
    parser.add_argument(
        "--ab-comparison",
        action="store_true",
        help="Run A/B comparison between code interpreter and standard",
    )

    args = parser.parse_args()

    if args.ab_comparison:
        run_ab_comparison(
            args.extractions_dir,
            args.output_dir,
            split=args.split if args.split != "all" else "train",
            model=args.model,
        )
    else:
        compute_dates_batch(
            args.extractions_dir,
            args.output_dir,
            split=args.split,
            use_code_interpreter=not args.no_code_interpreter,
            model=args.model,
        )
