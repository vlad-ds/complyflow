#!/usr/bin/env python3
"""
Extract metadata from CUAD dataset for selected contracts.

Usage:
    python extract_metadata.py [train|test]

Requires CUAD_v1.zip in parent directory. Download from:
https://www.atticusprojectai.org/cuad
"""

import json
import csv
import zipfile
import shutil
import sys
from pathlib import Path

# Parse split argument
SPLIT = sys.argv[1] if len(sys.argv) > 1 else "train"
if SPLIT not in ("train", "test"):
    print(f"Usage: python extract_metadata.py [train|test]")
    print(f"Invalid split: {SPLIT}")
    sys.exit(1)

# Paths
SCRIPT_DIR = Path(__file__).parent
CUAD_ZIP = SCRIPT_DIR / "CUAD_v1.zip"
CUAD_DIR = SCRIPT_DIR / "CUAD_v1"

# Split-specific paths
if SPLIT == "train":
    CONTRACTS_JSON = SCRIPT_DIR / "contracts_to_extract.json"
    CONTRACTS_DIR = SCRIPT_DIR / "train" / "contracts"
    OUTPUT_JSON = SCRIPT_DIR / "train" / "metadata.json"
    OUTPUT_CSV = SCRIPT_DIR / "train" / "metadata.csv"
else:
    CONTRACTS_JSON = SCRIPT_DIR / "test_contracts_to_extract.json"
    CONTRACTS_DIR = SCRIPT_DIR / "test" / "contracts"
    OUTPUT_JSON = SCRIPT_DIR / "test" / "metadata.json"
    OUTPUT_CSV = SCRIPT_DIR / "test" / "metadata.csv"

# Metadata fields to extract
METADATA_FIELDS = [
    "Document Name",
    "Parties",
    "Agreement Date",
    "Effective Date",
    "Expiration Date",
    "Renewal Term",
    "Notice Period To Terminate Renewal",
    "Governing Law",
]


def load_contracts_config():
    """Load contract selection from contracts.json."""
    with open(CONTRACTS_JSON, 'r') as f:
        return json.load(f)


def extract_cuad_zip():
    """Extract CUAD zip file if not already extracted."""
    if not CUAD_ZIP.exists():
        print(f"ERROR: CUAD dataset not found at {CUAD_ZIP}")
        print("Download from: https://www.atticusprojectai.org/cuad")
        return False

    if not CUAD_DIR.exists():
        print(f"Extracting {CUAD_ZIP}...")
        with zipfile.ZipFile(CUAD_ZIP, 'r') as z:
            z.extractall(CUAD_ZIP.parent)

    return True


def copy_contracts(contracts):
    """Copy selected contract PDFs to contracts directory."""
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    pdf_dir = CUAD_DIR / "full_contract_pdf"

    # Get all PDFs (case-insensitive)
    all_pdfs = list(pdf_dir.rglob("*.pdf")) + list(pdf_dir.rglob("*.PDF"))

    for c in contracts:
        found = False
        for pdf in all_pdfs:
            if c['match'] in pdf.name:
                shutil.copy(pdf, CONTRACTS_DIR / c['file'])
                found = True
                break
        if not found:
            print(f"WARNING: Could not find PDF matching {c['match']}")


def extract_metadata(contracts):
    """Extract metadata from CUAD JSON for selected contracts."""
    cuad_json = CUAD_DIR / "CUAD_v1.json"

    with open(cuad_json, 'r') as f:
        data = json.load(f)

    # Build lookup
    lookup = {c['match']: c for c in contracts}
    results = []

    for contract in data['data']:
        matched = None
        for match_str in lookup:
            if match_str in contract['title']:
                matched = lookup[match_str]
                break

        if not matched:
            continue

        metadata = {
            "file": matched['file'],
            "original_filename": contract['title'] + ".pdf",
            "contract_type": matched['type'],
        }

        for para in contract['paragraphs']:
            for qa in para['qas']:
                if '"' not in qa['question']:
                    continue
                field = qa['question'].split('"')[1]
                if field not in METADATA_FIELDS:
                    continue

                if qa.get('answers') and not qa.get('is_impossible', False):
                    seen = set()
                    answers = []
                    for a in qa['answers']:
                        if a['text'] not in seen:
                            seen.add(a['text'])
                            answers.append(a['text'])
                    metadata[field] = answers
                else:
                    metadata[field] = []

        results.append(metadata)

    results.sort(key=lambda x: x['file'])
    return results


def save_json(results):
    """Save metadata as JSON."""
    with open(OUTPUT_JSON, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Saved {OUTPUT_JSON}")


def save_csv(results):
    """Save metadata as CSV."""
    fieldnames = ['file', 'original_filename', 'contract_type'] + METADATA_FIELDS

    with open(OUTPUT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = dict(r)
            for field in METADATA_FIELDS:
                if isinstance(row.get(field), list):
                    row[field] = ' | '.join(row[field])
            writer.writerow(row)

    print(f"Saved {OUTPUT_CSV}")


def main():
    print(f"CUAD Metadata Extractor ({SPLIT})\n")

    if not extract_cuad_zip():
        return

    # Ensure output directory exists
    CONTRACTS_DIR.parent.mkdir(parents=True, exist_ok=True)

    contracts = load_contracts_config()
    print(f"Loaded {len(contracts)} contracts from {CONTRACTS_JSON.name}")

    print("Copying contract PDFs...")
    copy_contracts(contracts)

    print("Extracting metadata...")
    results = extract_metadata(contracts)
    print(f"Found metadata for {len(results)} contracts")

    save_json(results)
    save_csv(results)
    print("\nDone!")


if __name__ == "__main__":
    main()
