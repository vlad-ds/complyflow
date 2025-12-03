#!/usr/bin/env python3
"""Test script for the Contract Intake API."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from api.services.extraction import process_contract, extract_text_from_bytes


def test_text_extraction():
    """Test PDF text extraction."""
    pdf_path = Path("cuad/train/contracts/01_service_gpaq.pdf")

    print(f"Reading PDF: {pdf_path}")
    pdf_bytes = pdf_path.read_bytes()
    print(f"PDF size: {len(pdf_bytes)} bytes")

    print("Extracting text...")
    text = extract_text_from_bytes(pdf_bytes)
    print(f"Extracted {len(text)} characters")
    print(f"First 500 chars:\n{text[:500]}")
    return text


def test_full_pipeline():
    """Test full extraction pipeline."""
    pdf_path = Path("cuad/train/contracts/01_service_gpaq.pdf")

    print(f"\n{'='*60}")
    print("FULL PIPELINE TEST")
    print(f"{'='*60}")

    print(f"Reading PDF: {pdf_path}")
    pdf_bytes = pdf_path.read_bytes()

    print("Running full pipeline (this takes 30-60 seconds)...")
    result = process_contract(pdf_bytes, pdf_path.name)

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")

    print(f"\nFilename: {result['filename']}")
    print(f"\nExtraction:")
    for key, value in result["extraction"].items():
        if isinstance(value, dict):
            normalized = value.get("normalized_value", value)
            print(f"  {key}: {normalized}")
        else:
            print(f"  {key}: {value}")

    print(f"\nComputed Dates:")
    for key, value in result["computed_dates"].items():
        print(f"  {key}: {value}")

    print(f"\nUsage:")
    print(f"  Extraction: {result['usage']['extraction']}")
    print(f"  Date computation: {result['usage']['date_computation']}")

    return result


def test_airtable():
    """Test Airtable storage."""
    from api.services.airtable import AirtableService

    print(f"\n{'='*60}")
    print("AIRTABLE TEST")
    print(f"{'='*60}")

    airtable = AirtableService()
    print(f"Connected to base: {airtable.base_id}")

    # List existing contracts
    contracts = airtable.list_contracts(limit=5)
    print(f"Found {len(contracts)} contracts")
    for c in contracts:
        print(f"  - {c['id']}: {c['fields'].get('filename', 'unknown')}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Contract Intake API")
    parser.add_argument("--text-only", action="store_true", help="Only test text extraction")
    parser.add_argument("--airtable", action="store_true", help="Test Airtable connection")
    parser.add_argument("--full", action="store_true", help="Run full pipeline test")

    args = parser.parse_args()

    if args.text_only:
        test_text_extraction()
    elif args.airtable:
        test_airtable()
    elif args.full:
        test_full_pipeline()
    else:
        # Default: run all tests
        test_text_extraction()
        test_airtable()
        print("\nTo run full pipeline test (takes 30-60s), use: --full")
