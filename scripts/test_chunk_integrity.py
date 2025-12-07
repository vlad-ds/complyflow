#!/usr/bin/env python3
"""
Chunk Integrity Test

Evaluates whether different chunking strategies preserve important sentences intact.
Pure text analysis - no embeddings, vector databases, or LLMs.

Usage:
    PYTHONPATH=src uv run python scripts/test_chunk_integrity.py
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class ChunkingStrategy:
    """A chunking configuration to test."""

    name: str
    chunk_size: int
    chunk_overlap: int


# Define strategies to test
STRATEGIES = [
    ChunkingStrategy("512/50", chunk_size=512, chunk_overlap=50),
    ChunkingStrategy("1024/100", chunk_size=1024, chunk_overlap=100),
    ChunkingStrategy("2048/200", chunk_size=2048, chunk_overlap=200),
]

# Paths
GOLDEN_DATASET_PATH = Path("output/regwatch/golden_dataset.json")
DATA_DIR = Path("output/regwatch/cache")


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for comparison (collapse multiple spaces/newlines)."""
    return re.sub(r"\s+", " ", text).strip()


def quote_found_in_chunks(quote: str, chunks: list[str]) -> bool:
    """Check if the target quote appears completely in any single chunk."""
    normalized_quote = normalize_whitespace(quote)

    for chunk in chunks:
        normalized_chunk = normalize_whitespace(chunk)
        if normalized_quote in normalized_chunk:
            return True

    return False


def load_document(source_file: str) -> str | None:
    """Load document text from source_file path (e.g., 'DORA/32022R2554.txt')."""
    file_path = DATA_DIR / source_file
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")


def chunk_document(text: str, strategy: ChunkingStrategy) -> list[str]:
    """Split document into chunks using the given strategy."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=strategy.chunk_size,
        chunk_overlap=strategy.chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    docs = splitter.create_documents([text])
    return [doc.page_content for doc in docs]


def run_integrity_test() -> None:
    """Run the chunk integrity test and print results."""
    # Load golden dataset
    if not GOLDEN_DATASET_PATH.exists():
        print(f"Error: Golden dataset not found at {GOLDEN_DATASET_PATH}")
        return

    with open(GOLDEN_DATASET_PATH) as f:
        golden_data = json.load(f)

    print(f"Loaded {len(golden_data)} test cases from golden dataset\n")

    # Cache documents to avoid re-reading
    doc_cache: dict[str, str] = {}

    # Results storage
    results: dict[str, dict] = {}

    for strategy in STRATEGIES:
        print(f"Testing Strategy {strategy.name} (size={strategy.chunk_size}, overlap={strategy.chunk_overlap})...")

        passes = 0
        fails = 0
        failures: list[dict] = []

        # Chunk cache for this strategy
        chunk_cache: dict[str, list[str]] = {}

        for item in golden_data:
            source_file = item["source_file"]
            target_quote = item["target_quote"]
            question = item.get("question", "N/A")

            # Load document if not cached
            if source_file not in doc_cache:
                doc_text = load_document(source_file)
                if doc_text is None:
                    print(f"  [SKIP] Document not found: {source_file}")
                    continue
                doc_cache[source_file] = doc_text

            # Chunk document if not cached for this strategy
            cache_key = f"{strategy.name}:{source_file}"
            if cache_key not in chunk_cache:
                chunk_cache[cache_key] = chunk_document(doc_cache[source_file], strategy)

            chunks = chunk_cache[cache_key]

            # Check if quote survives chunking
            if quote_found_in_chunks(target_quote, chunks):
                passes += 1
            else:
                fails += 1
                failures.append(
                    {
                        "source_file": source_file,
                        "question": question,
                        "quote_preview": target_quote[:80] + "..." if len(target_quote) > 80 else target_quote,
                        "quote_length": len(target_quote),
                    }
                )

        total = passes + fails
        score = (passes / total * 100) if total > 0 else 0

        results[strategy.name] = {
            "passes": passes,
            "fails": fails,
            "total": total,
            "score": score,
            "failures": failures,
        }

        print(f"  -> {passes}/{total} passed ({score:.1f}%)\n")

    # Print summary table
    print("\n" + "=" * 70)
    print("CHUNK INTEGRITY RESULTS")
    print("=" * 70)
    print()
    print("| Strategy | Chunk Size | Overlap | Passes | Fails | Integrity Score |")
    print("|----------|------------|---------|--------|-------|-----------------|")

    for strategy in STRATEGIES:
        r = results[strategy.name]
        print(
            f"| {strategy.name:8} | {strategy.chunk_size:10} | {strategy.chunk_overlap:7} | "
            f"{r['passes']:6} | {r['fails']:5} | {r['score']:14.1f}% |"
        )

    print()

    # Print failure details
    print("\n" + "=" * 70)
    print("FAILURE DETAILS")
    print("=" * 70)

    for strategy in STRATEGIES:
        r = results[strategy.name]
        if r["failures"]:
            print(f"\n### Strategy {strategy.name} - {len(r['failures'])} failures:")
            for failure in r["failures"]:
                print(f"  [FAIL] {failure['source_file']}")
                print(f"         Quote length: {failure['quote_length']} chars")
                print(f"         Question: {failure['question'][:70]}...")
                print(f'         Quote: "{failure["quote_preview"]}"')
                print()

    # Analysis
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)

    # Find longest failing quote per strategy
    for strategy in STRATEGIES:
        r = results[strategy.name]
        if r["failures"]:
            longest = max(r["failures"], key=lambda x: x["quote_length"])
            print(f"\n{strategy.name}: Longest failing quote = {longest['quote_length']} chars")
            print(f"  Chunk size = {strategy.chunk_size}, so quotes > {strategy.chunk_size - strategy.chunk_overlap} chars may split")
        else:
            print(f"\n{strategy.name}: All quotes preserved!")

    # Recommendation
    print("\n" + "-" * 70)
    best_strategy = max(STRATEGIES, key=lambda s: results[s.name]["score"])
    print(f"RECOMMENDATION: Use Strategy {best_strategy.name} for best integrity ({results[best_strategy.name]['score']:.1f}%)")

    if results[best_strategy.name]["score"] < 100:
        print("\nNote: Some quotes are longer than the chunk size. Consider:")
        print("  1. Larger chunk sizes (e.g., 4096)")
        print("  2. Semantic chunking that respects paragraph boundaries")
        print("  3. Accepting some quote fragmentation and using overlap to compensate")


if __name__ == "__main__":
    run_integrity_test()
