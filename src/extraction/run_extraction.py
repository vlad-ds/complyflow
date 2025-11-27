#!/usr/bin/env python
"""Run contract metadata extraction on a text file.

Supports multiple LLM providers (Anthropic, OpenAI, Gemini) with model selection.

Usage:
    python -m extraction.run_extraction <contract_path> [--provider <provider>] [--model <model>]

Examples:
    # Use default (Anthropic Sonnet)
    python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt

    # Use OpenAI GPT-4.1
    python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt --provider openai

    # Use Gemini Flash
    python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt --provider gemini --model flash
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction.extract import extract_contract_metadata, format_extraction_result
from llm import get_provider, PROVIDERS


def main():
    parser = argparse.ArgumentParser(
        description="Extract contract metadata using LLM providers"
    )
    parser.add_argument("contract_path", type=Path, help="Path to contract text file")
    parser.add_argument(
        "--provider", "-p",
        type=str,
        default="anthropic",
        choices=list(PROVIDERS.keys()),
        help="LLM provider (default: anthropic)",
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="Model to use (provider-specific, uses default if not specified)",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output JSON path (default: output/<provider>/<contract_name>_extraction.json)",
    )
    args = parser.parse_args()

    # Resolve paths
    contract_path = args.contract_path
    if not contract_path.is_absolute():
        contract_path = Path.cwd() / contract_path

    if not contract_path.exists():
        print(f"Error: Contract file not found: {contract_path}")
        sys.exit(1)

    # Default output path with provider subfolder
    output_dir = Path(__file__).parent.parent.parent / "output" / args.provider
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = args.output
    if output_path is None:
        output_path = output_dir / f"{contract_path.stem}_extraction.json"

    # Initialize provider
    provider = get_provider(args.provider, model=args.model)

    # Run extraction
    print(f"Provider: {args.provider}")
    print(f"Model: {args.model or provider.default_model}")
    print(f"Extracting from: {contract_path.name}")
    print("-" * 60)

    result = extract_contract_metadata(provider, contract_path, model=args.model)

    # Print formatted result
    print(format_extraction_result(result))

    # Build JSON output
    llm_resp = getattr(result, "_llm_response", None)
    output_data = {
        "source_file": contract_path.name,
        "provider": args.provider,
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
            "model": llm_resp.model if llm_resp else None,
            "input_tokens": llm_resp.input_tokens if llm_resp else None,
            "output_tokens": llm_resp.output_tokens if llm_resp else None,
        },
    }

    # Save JSON
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nJSON saved to: {output_path}")


if __name__ == "__main__":
    main()
