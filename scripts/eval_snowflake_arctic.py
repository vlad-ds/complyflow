#!/usr/bin/env python3
"""
Snowflake Arctic Embed Evaluation

Tests the production embedding model (snowflake-arctic-embed-m-long) against
our golden dataset using Qdrant Cloud.

Prerequisites:
    Run indexing first: PYTHONPATH=src uv run python scripts/index_regwatch.py

Usage:
    PYTHONPATH=src uv run python scripts/eval_snowflake_arctic.py
"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from tqdm import tqdm

from regwatch.embeddings import DocumentEmbedder, MODEL_NAME, EMBEDDING_DIM, RetrievalConfig

load_dotenv()

# Configuration
retrieval_config = RetrievalConfig()
TOP_K = retrieval_config.top_k
COLLECTION_NAME = retrieval_config.collection_name

# Paths
GOLDEN_DATASET_PATH = Path("output/regwatch/golden_dataset.json")

# Qdrant Cloud
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for comparison."""
    return re.sub(r"\s+", " ", text).strip()


def quote_in_results(quote: str, results: list[dict]) -> bool:
    """Check if target quote appears in any retrieved chunk."""
    normalized_quote = normalize_whitespace(quote)

    for result in results:
        normalized_text = normalize_whitespace(result["text"])
        if normalized_quote in normalized_text:
            return True

    return False


def run_evaluation() -> None:
    """Run the Snowflake Arctic embedding evaluation using Qdrant Cloud."""
    print("=" * 70)
    print("SNOWFLAKE ARCTIC EMBED EVALUATION (Qdrant Cloud)")
    print(f"Model: {MODEL_NAME}")
    print(f"Embedding Dimension: {EMBEDDING_DIM}")
    print(f"Top-K: {TOP_K}")
    print("=" * 70)

    # Check Qdrant credentials
    if not QDRANT_URL or not QDRANT_API_KEY:
        print("\nError: QDRANT_URL and QDRANT_API_KEY must be set in .env")
        return

    # Load golden dataset
    if not GOLDEN_DATASET_PATH.exists():
        print(f"Error: Golden dataset not found at {GOLDEN_DATASET_PATH}")
        return

    with open(GOLDEN_DATASET_PATH) as f:
        golden_data = json.load(f)

    print(f"\nLoaded {len(golden_data)} test queries")

    # Initialize embedding model (only for query embedding)
    print(f"\nInitializing embedding model ({MODEL_NAME})...")
    embedder = DocumentEmbedder()

    # Connect to Qdrant Cloud
    print(f"\nConnecting to Qdrant Cloud...")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Verify collection exists
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        print(f"\nError: Collection '{COLLECTION_NAME}' not found")
        print("Run indexing first: PYTHONPATH=src uv run python scripts/index_regwatch.py")
        return

    collection_info = client.get_collection(collection_name=COLLECTION_NAME)
    print(f"Found collection with {collection_info.points_count} indexed chunks")

    # Run evaluation
    print("\n" + "=" * 70)
    print("EVALUATING RETRIEVAL")
    print("=" * 70)

    hits = 0
    misses = []

    for item in tqdm(golden_data, desc="Evaluating"):
        question = item["question"]
        target_quote = item["target_quote"]
        source_file = item["source_file"]

        # Embed query using production embedder
        query_embedding = embedder.embed_query(question)

        # Search using query_points (qdrant-client >= 1.12)
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            limit=TOP_K,
        )

        # Convert results to our format
        retrieved = [{"text": r.payload["text"], "source_file": r.payload["source_file"], "score": r.score} for r in results.points]

        # Check if quote is in results
        if quote_in_results(target_quote, retrieved):
            hits += 1
        else:
            misses.append(
                {
                    "question": question,
                    "target_quote": target_quote[:100] + "..." if len(target_quote) > 100 else target_quote,
                    "source_file": source_file,
                    "top_result_file": retrieved[0]["source_file"] if retrieved else "N/A",
                    "top_score": retrieved[0]["score"] if retrieved else 0,
                }
            )

    # Results
    total = len(golden_data)
    hit_rate = (hits / total * 100) if total > 0 else 0

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"\nRetrieval Score: {hits}/{total} ({hit_rate:.1f}%)")

    if misses:
        print(f"\n{len(misses)} MISSES:")
        print("-" * 70)
        for miss in misses:
            print(f'\n[MISS] Question: "{miss["question"][:70]}..."')
            print(f'       Expected from: {miss["source_file"]}')
            print(f'       Top result from: {miss["top_result_file"]} (score: {miss["top_score"]:.3f})')
            print(f'       Expected Quote: "{miss["target_quote"]}"')

    # Comparison with baseline
    print("\n" + "=" * 70)
    print("MODEL COMPARISON")
    print("=" * 70)
    print(f"\n{'Model':<40} {'MTEB Retrieval':<15} {'Our Eval':<10}")
    print("-" * 65)
    print(f"{'BGE-Small-EN-v1.5 (baseline)':<40} {'53.86':<15} {'85.0%':<10}")
    print(f"{'Snowflake Arctic Embed M Long':<40} {'57.02':<15} {f'{hit_rate:.1f}%':<10}")

    improvement = hit_rate - 85.0
    if improvement > 0:
        print(f"\nSnowflake Arctic improves retrieval by +{improvement:.1f} percentage points")
    elif improvement < 0:
        print(f"\nSnowflake Arctic is {abs(improvement):.1f} percentage points below baseline")
    else:
        print("\nBoth models perform equally on this dataset")

    # Analysis
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)

    if hit_rate >= 90:
        print(f"\nExcellent! {hit_rate:.1f}% hit rate - Snowflake Arctic is production-ready.")
    elif hit_rate >= 80:
        print(f"\nGood. {hit_rate:.1f}% hit rate is acceptable for production.")
        print("Consider: hybrid search or reranking for further improvements.")
    else:
        print(f"\nPoor. {hit_rate:.1f}% hit rate needs investigation.")

    # Check if misses are from wrong documents
    if misses:
        wrong_doc_count = sum(1 for m in misses if m["top_result_file"] != m["source_file"])
        print(f"\nOf {len(misses)} misses, {wrong_doc_count} retrieved from wrong document entirely.")


if __name__ == "__main__":
    run_evaluation()
