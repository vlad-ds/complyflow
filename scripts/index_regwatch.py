#!/usr/bin/env python3
"""
Index Regulatory Documents to Qdrant Cloud

Indexes all regulatory documents from the cache directory to Qdrant Cloud
using Snowflake Arctic Embed M Long.

Usage:
    PYTHONPATH=src uv run python scripts/index_regwatch.py

Requires QDRANT_URL and QDRANT_API_KEY in .env
"""

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

from regwatch.embeddings import DocumentEmbedder, MODEL_NAME, EMBEDDING_DIM, RetrievalConfig
from regwatch.metadata import extract_metadata

load_dotenv()

# Configuration
CHUNK_SIZE = 2048
CHUNK_OVERLAP = 200
retrieval_config = RetrievalConfig()
COLLECTION_NAME = retrieval_config.collection_name

# Paths
DATA_DIR = Path("output/regwatch/cache")

# Qdrant Cloud
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


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


def run_indexing() -> None:
    """Index all documents to Qdrant Cloud."""
    print("=" * 70)
    print("REGWATCH DOCUMENT INDEXING (Qdrant Cloud)")
    print(f"Model: {MODEL_NAME}")
    print(f"Embedding Dimension: {EMBEDDING_DIM}")
    print(f"Chunk Size: {CHUNK_SIZE}, Overlap: {CHUNK_OVERLAP}")
    print(f"Qdrant URL: {QDRANT_URL}")
    print("=" * 70)

    # Check Qdrant credentials
    if not QDRANT_URL or not QDRANT_API_KEY:
        print("\nError: QDRANT_URL and QDRANT_API_KEY must be set in .env")
        return

    # Load and chunk documents
    print("\nLoading documents...")
    documents = load_documents()
    print(f"Loaded {len(documents)} documents")

    print("\nChunking documents...")
    chunks = chunk_documents(documents)
    print(f"Created {len(chunks)} chunks")

    # Initialize embedding model
    print(f"\nInitializing embedding model ({MODEL_NAME})...")
    embedder = DocumentEmbedder()
    print(f"Embedding dimension: {embedder.dimension}")

    # Initialize Qdrant Cloud
    print("\nConnecting to Qdrant Cloud...")
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Check if collection exists
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in collections:
        print(f"Collection '{COLLECTION_NAME}' exists. Deleting and recreating...")
        client.delete_collection(collection_name=COLLECTION_NAME)

    # Create collection
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=embedder.dimension, distance=Distance.COSINE),
    )
    print(f"Created collection: {COLLECTION_NAME}")

    # Index chunks
    print("\nIndexing chunks (this takes ~14 minutes)...")
    batch_size = 32
    point_id = 0
    for i in tqdm(range(0, len(chunks), batch_size), desc="Indexing"):
        batch = chunks[i : i + batch_size]
        texts = [c["text"] for c in batch]

        # Generate embeddings using our production embedder
        embeddings = embedder.embed_texts(texts)

        # Create points with full metadata payload
        points = []
        for j in range(len(batch)):
            # Use chunk dict as payload (all metadata already flattened)
            payload = {k: v for k, v in batch[j].items() if k != "id"}
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embeddings[j],
                    payload=payload,
                )
            )
            point_id += 1

        client.upsert(collection_name=COLLECTION_NAME, points=points)

    print(f"\nIndexed {len(chunks)} chunks to Qdrant Cloud")

    # Verify
    collection_info = client.get_collection(collection_name=COLLECTION_NAME)
    print(f"Collection now has {collection_info.points_count} points")

    print("\n" + "=" * 70)
    print("INDEXING COMPLETE")
    print("=" * 70)
    print(f"\nRun evaluation with: PYTHONPATH=src uv run python scripts/eval_snowflake_arctic.py")


if __name__ == "__main__":
    run_indexing()
