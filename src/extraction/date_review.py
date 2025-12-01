"""Review table generator for date computation results.

Generates CSV and markdown tables for manual review of computed dates.
"""

import csv
import json
from pathlib import Path
from typing import Literal


def format_date_obj(date_val) -> str:
    """Format a date object/value for display.

    Args:
        date_val: Date value (dict with year/month/day, string, or null).

    Returns:
        Formatted string representation.
    """
    if date_val is None:
        return "null"
    if isinstance(date_val, str):
        return date_val
    if isinstance(date_val, dict):
        return f"{date_val['year']}-{date_val['month']:02d}-{date_val['day']:02d}"
    return str(date_val)


def needs_review(input_data: dict, computed_dates: dict) -> bool:
    """Determine if a result needs manual review.

    A result needs review if:
    - expiration_date was computed from a relative term
    - any field has a special marker (perpetual, conditional)

    Args:
        input_data: The input date fields from extraction.
        computed_dates: The computed date objects.

    Returns:
        True if manual review is recommended.
    """
    # Check for special markers
    for field in ["agreement_date", "effective_date", "expiration_date"]:
        val = computed_dates.get(field)
        if isinstance(val, str) and val in ("perpetual", "conditional"):
            return True

    # Check if expiration_date was computed from relative term
    exp_input = input_data.get("expiration_date", {}).get("normalized_value", "")
    if exp_input and not _is_iso_date(exp_input):
        return True

    return False


def _is_iso_date(value: str) -> bool:
    """Check if a string is an ISO date (YYYY-MM-DD)."""
    if not value:
        return False
    parts = value.split("-")
    if len(parts) != 3:
        return False
    try:
        int(parts[0])
        int(parts[1])
        int(parts[2])
        return True
    except ValueError:
        return False


def generate_review_csv(
    results_dir: Path,
    output_path: Path,
) -> Path:
    """Generate a CSV review table from date computation results.

    Args:
        results_dir: Directory containing *_dates.json result files.
        output_path: Path to save the CSV file.

    Returns:
        Path to the generated CSV file.
    """
    result_files = sorted(results_dir.glob("*_dates.json"))

    rows = []
    for result_file in result_files:
        with open(result_file) as f:
            result = json.load(f)

        input_data = result.get("input_data", {})
        computed = result.get("computed_dates", {})

        row = {
            "contract": result.get("source_file", "").replace("_extraction.json", ""),
            # Agreement date
            "agreement_input": input_data.get("agreement_date", {}).get(
                "normalized_value", ""
            ),
            "agreement_output": format_date_obj(computed.get("agreement_date")),
            # Effective date
            "effective_input": input_data.get("effective_date", {}).get(
                "normalized_value", ""
            ),
            "effective_output": format_date_obj(computed.get("effective_date")),
            # Expiration date
            "expiration_input": input_data.get("expiration_date", {}).get(
                "normalized_value", ""
            ),
            "expiration_output": format_date_obj(computed.get("expiration_date")),
            # Notice period and deadline
            "notice_period": input_data.get("notice_period", {}).get(
                "normalized_value", ""
            ),
            "notice_deadline": format_date_obj(computed.get("notice_deadline")),
            # Renewal term and first renewal date
            "renewal_term": input_data.get("renewal_term", {}).get(
                "normalized_value", ""
            ),
            "first_renewal_date": format_date_obj(computed.get("first_renewal_date")),
            # Metadata
            "needs_review": "YES" if needs_review(input_data, computed) else "",
            "code_interpreter": "YES" if result.get("code_interpreter_used") else "NO",
            "latency_s": f"{result.get('latency_seconds', 0):.1f}",
        }
        rows.append(row)

    # Write CSV
    fieldnames = [
        "contract",
        "agreement_input",
        "agreement_output",
        "effective_input",
        "effective_output",
        "expiration_input",
        "expiration_output",
        "notice_period",
        "notice_deadline",
        "renewal_term",
        "first_renewal_date",
        "needs_review",
        "code_interpreter",
        "latency_s",
    ]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated review CSV: {output_path}")
    print(f"  Total contracts: {len(rows)}")
    print(f"  Needs review: {sum(1 for r in rows if r['needs_review'] == 'YES')}")

    return output_path


def generate_review_markdown(
    results_dir: Path,
    output_path: Path,
) -> Path:
    """Generate a markdown review table from date computation results.

    Args:
        results_dir: Directory containing *_dates.json result files.
        output_path: Path to save the markdown file.

    Returns:
        Path to the generated markdown file.
    """
    result_files = sorted(results_dir.glob("*_dates.json"))

    lines = [
        "# Date Computation Review",
        "",
        "## Base Dates",
        "",
        "| Contract | Agreement | Effective | Expiration Input | Expiration Output |",
        "|----------|-----------|-----------|------------------|-------------------|",
    ]

    for result_file in result_files:
        with open(result_file) as f:
            result = json.load(f)

        input_data = result.get("input_data", {})
        computed = result.get("computed_dates", {})

        contract = result.get("source_file", "").replace("_extraction.json", "")
        agreement = format_date_obj(computed.get("agreement_date"))
        effective = format_date_obj(computed.get("effective_date"))
        exp_input = input_data.get("expiration_date", {}).get("normalized_value", "")
        exp_output = format_date_obj(computed.get("expiration_date"))

        # Truncate long expiration inputs for readability
        if len(exp_input) > 40:
            exp_input = exp_input[:37] + "..."

        lines.append(
            f"| {contract} | {agreement} | {effective} | {exp_input} | {exp_output} |"
        )

    # Add derived dates table
    lines.extend([
        "",
        "## Derived Dates",
        "",
        "| Contract | Notice Period | Notice Deadline | Renewal Term | First Renewal |",
        "|----------|---------------|-----------------|--------------|---------------|",
    ])

    for result_file in result_files:
        with open(result_file) as f:
            result = json.load(f)

        input_data = result.get("input_data", {})
        computed = result.get("computed_dates", {})

        contract = result.get("source_file", "").replace("_extraction.json", "")
        notice_period = input_data.get("notice_period", {}).get("normalized_value", "")
        notice_deadline = format_date_obj(computed.get("notice_deadline"))
        renewal_term = input_data.get("renewal_term", {}).get("normalized_value", "")
        first_renewal = format_date_obj(computed.get("first_renewal_date"))

        # Truncate long inputs
        if len(renewal_term) > 25:
            renewal_term = renewal_term[:22] + "..."

        lines.append(
            f"| {contract} | {notice_period} | {notice_deadline} | {renewal_term} | {first_renewal} |"
        )

    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Generated review markdown: {output_path}")
    return output_path


def generate_comparison_table(
    ci_results_dir: Path,
    std_results_dir: Path,
    output_path: Path,
) -> Path:
    """Generate a comparison table between code interpreter and standard results.

    Args:
        ci_results_dir: Directory with code interpreter results.
        std_results_dir: Directory with standard results.
        output_path: Path to save the comparison CSV.

    Returns:
        Path to the generated CSV file.
    """
    ci_files = {f.name: f for f in ci_results_dir.glob("*_dates.json")}
    std_files = {f.name: f for f in std_results_dir.glob("*_dates.json")}

    rows = []
    all_files = set(ci_files.keys()) | set(std_files.keys())

    for filename in sorted(all_files):
        ci_data = {}
        std_data = {}

        if filename in ci_files:
            with open(ci_files[filename]) as f:
                ci_data = json.load(f)
        if filename in std_files:
            with open(std_files[filename]) as f:
                std_data = json.load(f)

        ci_computed = ci_data.get("computed_dates", {})
        std_computed = std_data.get("computed_dates", {})

        # Compare each field
        for field in ["agreement_date", "effective_date", "expiration_date"]:
            ci_val = format_date_obj(ci_computed.get(field))
            std_val = format_date_obj(std_computed.get(field))
            match = "YES" if ci_val == std_val else "NO"

            rows.append(
                {
                    "contract": filename.replace("_dates.json", ""),
                    "field": field,
                    "code_interpreter": ci_val,
                    "standard": std_val,
                    "match": match,
                }
            )

    fieldnames = ["contract", "field", "code_interpreter", "standard", "match"]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    matches = sum(1 for r in rows if r["match"] == "YES")
    total = len(rows)
    print(f"Generated comparison CSV: {output_path}")
    print(f"  Match rate: {matches}/{total} ({matches/total:.1%})")

    return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate review tables for date computation")
    parser.add_argument(
        "--results-dir",
        type=Path,
        required=True,
        help="Directory containing *_dates.json result files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output file path (CSV or MD based on extension)",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "markdown"],
        default="csv",
        help="Output format",
    )

    args = parser.parse_args()

    if args.format == "csv":
        generate_review_csv(args.results_dir, args.output)
    else:
        generate_review_markdown(args.results_dir, args.output)
