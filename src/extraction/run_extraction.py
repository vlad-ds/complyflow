#!/usr/bin/env python
"""Run contract metadata extraction on a text file.

Usage:
    python -m extraction.run_extraction <contract_path> [--output <output_path>]

Example:
    python -m extraction.run_extraction temp/extracted_text/06_license_morganstanley.txt
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction import extract_contract_metadata, format_extraction_result
from llm import get_anthropic_client


def main():
    parser = argparse.ArgumentParser(description="Extract contract metadata")
    parser.add_argument("contract_path", type=Path, help="Path to contract text file")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSON path (default: output/<contract_name>_extraction.json)"
    )
    args = parser.parse_args()

    # Resolve paths
    contract_path = args.contract_path
    if not contract_path.is_absolute():
        contract_path = Path.cwd() / contract_path

    if not contract_path.exists():
        print(f"Error: Contract file not found: {contract_path}")
        sys.exit(1)

    # Default output path
    output_dir = Path(__file__).parent.parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    output_path = args.output
    if output_path is None:
        output_path = output_dir / f"{contract_path.stem}_extraction.json"

    # Run extraction
    print(f"Extracting from: {contract_path.name}")
    print("-" * 60)

    client = get_anthropic_client()
    result = extract_contract_metadata(client, contract_path)

    # Print formatted result
    print(format_extraction_result(result))

    # Build JSON output
    output_data = {
        "source_file": contract_path.name,
        "extraction": {
            "parties": {
                "raw_snippet": result.parties.raw_snippet,
                "reasoning": result.parties.reasoning,
                "normalized_value": result.parties.normalized_value,
            },
            "contract_type": {
                "raw_snippet": result.contract_type.raw_snippet,
                "reasoning": result.contract_type.reasoning,
                "normalized_value": result.contract_type.normalized_value,
            },
            "notice_period": {
                "raw_snippet": result.notice_period.raw_snippet,
                "reasoning": result.notice_period.reasoning,
                "normalized_value": result.notice_period.normalized_value,
            },
            "expiration_date": {
                "raw_snippet": result.expiration_date.raw_snippet,
                "reasoning": result.expiration_date.reasoning,
                "normalized_value": result.expiration_date.normalized_value,
            },
            "renewal_term": {
                "raw_snippet": result.renewal_term.raw_snippet,
                "reasoning": result.renewal_term.reasoning,
                "normalized_value": result.renewal_term.normalized_value,
            },
        },
        "usage": {
            "model": result._raw_response.model if hasattr(result, "_raw_response") else None,
            "input_tokens": result._raw_response.usage.input_tokens if hasattr(result, "_raw_response") else None,
            "output_tokens": result._raw_response.usage.output_tokens if hasattr(result, "_raw_response") else None,
        },
    }

    # Save JSON
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nJSON saved to: {output_path}")


if __name__ == "__main__":
    main()
