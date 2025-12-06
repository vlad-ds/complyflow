#!/usr/bin/env python3
"""
Retrieval Evaluation Script

Tests end-to-end RAG retrieval using FastEmbed embeddings and in-memory Qdrant.
Validates that 2048-character chunks can be effectively retrieved for regulatory Q&A.

Usage:
    PYTHONPATH=src uv run python scripts/eval_retrieval.py
"""

import json
import re
import uuid
from pathlib import Path

from fastembed import TextEmbedding
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

from regwatch.metadata import extract_metadata

# Configuration
CHUNK_SIZE = 2048
CHUNK_OVERLAP = 200
TOP_K = 5
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
COLLECTION_NAME = "regwatch_eval"

# Paths
GOLDEN_DATASET_PATH = Path("output/regwatch/golden_dataset.json")
DATA_DIR = Path("output/regwatch/cache")


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for comparison."""
    return re.sub(r"\s+", " ", text).strip()


def load_documents() -> list[dict]:
    """Load all documents from the data directory with metadata."""
    documents = []

    for topic_dir in DATA_DIR.iterdir():
        if not topic_dir.is_dir():
            continue

        topic = topic_dir.name  # e.g., "DORA", "MiCA"

        for file_path in topic_dir.glob("*.txt"):
            content = file_path.read_text(encoding="utf-8")
            celex = file_path.stem  # filename without extension
            rel_path = f"{topic}/{file_path.name}"

            # Extract metadata (no LLM calls - pure parsing)
            metadata = extract_metadata(celex, content, topic=topic)

            documents.append({
                "source_file": rel_path,
                "content": content,
                "metadata": metadata,
            })

    return documents


def chunk_documents(documents: list[dict]) -> list[dict]:
    """Split documents into chunks with metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for doc in documents:
        splits = splitter.split_text(doc["content"])
        metadata = doc["metadata"]

        for i, chunk_text in enumerate(splits):
            # Get chunk metadata from document metadata
            chunk_meta = metadata.to_chunk_metadata(
                chunk_index=i,
                source_file=doc["source_file"],
            )
            chunk_meta["text"] = chunk_text  # Add text to payload

            chunks.append({
                "id": str(uuid.uuid4()),
                "text": chunk_text,
                **chunk_meta,  # Flatten metadata into chunk
            })

    return chunks


def quote_in_results(quote: str, results: list[dict]) -> bool:
    """Check if target quote appears in any retrieved chunk."""
    normalized_quote = normalize_whitespace(quote)

    for result in results:
        normalized_text = normalize_whitespace(result["text"])
        if normalized_quote in normalized_text:
            return True

    return False


def run_evaluation() -> None:
    """Run the retrieval evaluation."""
    print("=" * 70)
    print("RETRIEVAL EVALUATION")
    print(f"Model: {EMBEDDING_MODEL}")
    print(f"Chunk Size: {CHUNK_SIZE}, Overlap: {CHUNK_OVERLAP}")
    print(f"Top-K: {TOP_K}")
    print("=" * 70)

    # Load golden dataset
    if not GOLDEN_DATASET_PATH.exists():
        print(f"Error: Golden dataset not found at {GOLDEN_DATASET_PATH}")
        return

    with open(GOLDEN_DATASET_PATH) as f:
        golden_data = json.load(f)

    print(f"\nLoaded {len(golden_data)} test queries")

    # Load and chunk documents
    print("\nLoading documents...")
    documents = load_documents()
    print(f"Loaded {len(documents)} documents")

    print("\nChunking documents...")
    chunks = chunk_documents(documents)
    print(f"Created {len(chunks)} chunks")

    # Initialize embedding model
    print(f"\nInitializing embedding model ({EMBEDDING_MODEL})...")
    embedder = TextEmbedding(model_name=EMBEDDING_MODEL)

    # Get embedding dimension from a test embedding
    test_embedding = list(embedder.embed(["test"]))[0]
    embedding_dim = len(test_embedding)
    print(f"Embedding dimension: {embedding_dim}")

    # Initialize Qdrant (in-memory)
    print("\nInitializing Qdrant (in-memory)...")
    client = QdrantClient(":memory:")

    # Create collection
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
    )

    # Index chunks
    print("\nIndexing chunks...")
    batch_size = 100
    for i in tqdm(range(0, len(chunks), batch_size), desc="Indexing"):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]

        # Generate embeddings
        embeddings = list(embedder.embed(texts))

        # Create points with full metadata payload
        points = []
        for j in range(len(batch)):
            # Use chunk dict as payload (all metadata already flattened)
            payload = {k: v for k, v in batch[j].items() if k != "id"}
            points.append(
                PointStruct(
                    id=j + i,
                    vector=embeddings[j].tolist(),
                    payload=payload,
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)

    print(f"Indexed {len(chunks)} chunks into Qdrant")

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

        # Embed query
        query_embedding = list(embedder.embed([question]))[0]

        # Search using query_points (qdrant-client >= 1.12)
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding.tolist(),
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

    # Analysis
    print("\n" + "=" * 70)
    print("ANALYSIS")
    print("=" * 70)

    if hit_rate >= 90:
        print(f"\nExcellent! {hit_rate:.1f}% hit rate indicates the 2048-chunk strategy works well.")
    elif hit_rate >= 70:
        print(f"\nGood. {hit_rate:.1f}% hit rate is acceptable but could be improved.")
        print("Consider: hybrid search, reranking, or query expansion.")
    else:
        print(f"\nPoor. {hit_rate:.1f}% hit rate suggests issues with:")
        print("  - Chunk size too large (embedding dilution)")
        print("  - Embedding model mismatch with regulatory domain")
        print("  - Query formulation")

    # Check if misses are from wrong documents
    if misses:
        wrong_doc_count = sum(1 for m in misses if m["top_result_file"] != m["source_file"])
        print(f"\nOf {len(misses)} misses, {wrong_doc_count} retrieved from wrong document entirely.")


if __name__ == "__main__":
    run_evaluation()
