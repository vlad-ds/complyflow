#!/usr/bin/env python
"""Run contract metadata extraction on a text file.

Supports multiple LLM providers (Anthropic, OpenAI, Gemini) with model selection.
Output is organized by model name for easy comparison.

Usage:
    python -m extraction.run_extraction <contract_path> [--provider <provider>] [--model <model>]

Examples:
    # Claude Sonnet 4.5 (default)
    python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt

    # Claude Haiku
    python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt -p anthropic -m haiku

    # GPT-5
    python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt -p openai -m gpt-5

    # GPT-5-mini
    python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt -p openai -m gpt-5-mini

    # Gemini 2.5 Flash
    python -m extraction.run_extraction temp/extracted_text/train/06_license_morganstanley.txt -p gemini
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
        help="Output JSON path (default: output/<model>/<contract_name>_extraction.json)",
    )
    args = parser.parse_args()

    # Resolve paths
    contract_path = args.contract_path
    if not contract_path.is_absolute():
        contract_path = Path.cwd() / contract_path

    if not contract_path.exists():
        print(f"Error: Contract file not found: {contract_path}")
        sys.exit(1)

    # Initialize provider
    provider = get_provider(args.provider, model=args.model)

    # Get the actual model name for the output folder
    model_name = args.model or provider.default_model
    # Use short name if it was resolved from a short name
    model_folder = args.model if args.model else list(provider.MODELS.keys())[list(provider.MODELS.values()).index(provider.default_model)]

    # Default output path with model subfolder
    output_dir = Path(__file__).parent.parent.parent / "output" / model_folder
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = args.output
    if output_path is None:
        output_path = output_dir / f"{contract_path.stem}_extraction.json"

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
    def field_to_dict(field):
        return {
            "raw_snippet": field.raw_snippet,
            "reasoning": field.reasoning,
            "normalized_value": field.normalized_value,
        }

    output_data = {
        "source_file": contract_path.name,
        "provider": args.provider,
        "extraction": {
            "parties": field_to_dict(result.parties),
            "contract_type": field_to_dict(result.contract_type),
            "agreement_date": field_to_dict(result.agreement_date),
            "effective_date": field_to_dict(result.effective_date),
            "expiration_date": field_to_dict(result.expiration_date),
            "governing_law": field_to_dict(result.governing_law),
            "notice_period": field_to_dict(result.notice_period),
            "renewal_term": field_to_dict(result.renewal_term),
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
