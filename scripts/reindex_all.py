#!/usr/bin/env python3
"""
Re-index all cached documents to Qdrant with new metadata headers.

This script:
1. Deletes all points from Qdrant collection
2. Clears the local registry
3. Re-chunks all cached documents with metadata headers
4. Re-embeds and uploads to Qdrant

Usage:
    PYTHONPATH=src uv run python scripts/reindex_all.py
    PYTHONPATH=src uv run python scripts/reindex_all.py --dry-run
"""

import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from regwatch.chunking import chunk_document
from regwatch.embeddings import get_embedder
from regwatch.ingest_config import IngestConfig
from regwatch.metadata import extract_metadata
from regwatch.qdrant_client import RegwatchQdrant
from regwatch.storage import LOCAL_CACHE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_all_cached_documents() -> list[tuple[str, str, str]]:
    """
    Get all cached documents from local storage.

    Returns:
        List of (topic, celex, file_path) tuples
    """
    documents = []

    for topic_dir in LOCAL_CACHE_DIR.iterdir():
        if not topic_dir.is_dir():
            continue

        topic = topic_dir.name
        if topic not in ["DORA", "MiCA"]:
            continue

        for doc_file in topic_dir.glob("*.txt"):
            celex = doc_file.stem
            documents.append((topic, celex, str(doc_file)))

    return documents


def clear_qdrant_collection(qdrant: RegwatchQdrant, dry_run: bool = False) -> int:
    """
    Delete all points from the Qdrant collection.

    Returns:
        Number of points deleted
    """
    try:
        stats = qdrant.get_collection_stats()
        points_count = stats.get("points_count", 0)

        if dry_run:
            logger.info(f"[DRY RUN] Would delete {points_count} points from Qdrant")
            return points_count

        if points_count > 0:
            # Delete all points by recreating the collection
            qdrant.client.delete_collection(qdrant.config.collection_name)
            logger.info(f"Deleted collection with {points_count} points")

            # Recreate collection
            qdrant.ensure_collection_exists()
            logger.info("Recreated empty collection")

        return points_count
    except Exception as e:
        logger.error(f"Failed to clear Qdrant: {e}")
        return 0


def clear_local_registry() -> None:
    """Clear the local registry file."""
    registry_file = LOCAL_CACHE_DIR / "indexed_documents.txt"
    if registry_file.exists():
        registry_file.unlink()
        logger.info(f"Deleted local registry: {registry_file}")


def reindex_document(
    topic: str,
    celex: str,
    file_path: str,
    config: IngestConfig,
    embedder,
    qdrant: RegwatchQdrant,
    dry_run: bool = False,
) -> int:
    """
    Re-index a single document.

    Returns:
        Number of chunks indexed
    """
    # Read content
    content = Path(file_path).read_text()

    # Extract metadata
    metadata = extract_metadata(
        celex=celex,
        content=content,
        topic=topic,
    )

    # Chunk with new metadata headers
    source_file = f"{topic}/{celex}.txt"
    chunks = chunk_document(content, metadata, source_file, config)

    if dry_run:
        logger.info(f"[DRY RUN] {celex}: {len(chunks)} chunks")
        # Show first chunk preview
        if chunks:
            preview = chunks[0]["text"][:300].replace("\n", " ")
            logger.info(f"  Preview: {preview}...")
        return len(chunks)

    # Generate embeddings
    texts = [c["text"] for c in chunks]
    embeddings = []
    batch_size = 16

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = embedder.embed_texts(batch)
        embeddings.extend(batch_embeddings)

    # Upsert to Qdrant (deterministic IDs will overwrite existing)
    qdrant.upsert_chunks(celex, chunks, embeddings)

    logger.info(f"Indexed {celex}: {len(chunks)} chunks")
    return len(chunks)


def main():
    parser = argparse.ArgumentParser(
        description="Re-index all cached documents with new metadata headers"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("RE-INDEX ALL DOCUMENTS")
    print("=" * 60)

    # Get all cached documents
    documents = get_all_cached_documents()
    print(f"Found {len(documents)} documents in local cache")

    if not documents:
        print("No documents found!")
        return

    # Initialize components
    config = IngestConfig()
    qdrant = RegwatchQdrant(config)

    # Clear Qdrant
    print("\n--- Clearing Qdrant ---")
    deleted = clear_qdrant_collection(qdrant, dry_run=args.dry_run)
    print(f"Cleared {deleted} points from Qdrant")

    # Clear local registry
    if not args.dry_run:
        clear_local_registry()
    else:
        print("[DRY RUN] Would clear local registry")

    # Initialize embedder
    print("\n--- Loading embedder ---")
    embedder = get_embedder()

    # Re-index all documents
    print("\n--- Re-indexing documents ---")
    total_chunks = 0

    for topic, celex, file_path in documents:
        try:
            chunks = reindex_document(
                topic=topic,
                celex=celex,
                file_path=file_path,
                config=config,
                embedder=embedder,
                qdrant=qdrant,
                dry_run=args.dry_run,
            )
            total_chunks += chunks
        except Exception as e:
            logger.error(f"Failed to index {celex}: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"Documents indexed: {len(documents)}")
    print(f"Total chunks: {total_chunks}")

    if not args.dry_run:
        # Verify
        stats = qdrant.get_collection_stats()
        print(f"Qdrant points: {stats.get('points_count', 'unknown')}")


if __name__ == "__main__":
    main()
