"""
Contract embedding pipeline.

Chunks contracts, embeds them, and stores in Qdrant.
"""

import logging
from typing import Any

from contracts.chunking import chunk_contract
from contracts.config import ContractEmbedConfig
from contracts.qdrant_client import ContractsQdrant
from regwatch.embeddings import get_embedder

logger = logging.getLogger(__name__)


def embed_and_store_contract(
    text: str,
    contract_id: str,
    filename: str,
    extraction: dict[str, Any],
    config: ContractEmbedConfig | None = None,
) -> dict:
    """
    Chunk, embed, and store a contract in Qdrant.

    Args:
        text: Full contract text (extracted from PDF)
        contract_id: Airtable record ID
        filename: Original PDF filename
        extraction: Extraction results dict with parties, contract_type, etc.
        config: Embedding configuration (uses defaults if not provided)

    Returns:
        Dict with:
        - contract_id: Airtable record ID
        - chunks_count: Number of chunks created
        - points_upserted: Number of points stored in Qdrant

    Raises:
        ValueError: If text is empty or Qdrant credentials not set
        Exception: If embedding or Qdrant operations fail
    """
    config = config or ContractEmbedConfig()

    if not text.strip():
        raise ValueError("Contract text is empty")

    logger.info(f"Embedding contract {contract_id} ({filename})")

    # Step 1: Chunk the contract
    chunks = chunk_contract(
        text=text,
        contract_id=contract_id,
        filename=filename,
        extraction=extraction,
        config=config,
    )
    logger.info(f"Created {len(chunks)} chunks for {contract_id}")

    if not chunks:
        raise ValueError("No chunks created from contract text")

    # Step 2: Embed chunks
    embedder = get_embedder()
    texts = [c["text"] for c in chunks]

    # Embed in batches to avoid OOM
    embeddings = []
    batch_size = config.embedding_batch_size
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        batch_embeddings = embedder.embed_texts(batch)
        embeddings.extend(batch_embeddings)
        logger.debug(f"Embedded batch {i // batch_size + 1}/{(len(texts) + batch_size - 1) // batch_size}")

    logger.info(f"Embedded {len(embeddings)} chunks for {contract_id}")

    # Step 3: Store in Qdrant
    qdrant = ContractsQdrant(config)
    qdrant.ensure_collection_exists()

    # Delete existing chunks for this contract (if re-uploading)
    if qdrant.is_indexed(contract_id):
        deleted = qdrant.delete_contract(contract_id)
        logger.info(f"Deleted {deleted} existing chunks for {contract_id}")

    points_upserted = qdrant.upsert_chunks(
        contract_id=contract_id,
        chunks=chunks,
        embeddings=embeddings,
    )

    logger.info(f"Stored {points_upserted} points for {contract_id}")

    return {
        "contract_id": contract_id,
        "chunks_count": len(chunks),
        "points_upserted": points_upserted,
    }


def delete_contract_embeddings(contract_id: str) -> int:
    """
    Delete all embeddings for a contract from Qdrant.

    Args:
        contract_id: Airtable record ID

    Returns:
        Number of points deleted
    """
    config = ContractEmbedConfig()
    qdrant = ContractsQdrant(config)

    try:
        qdrant.ensure_collection_exists()
        return qdrant.delete_contract(contract_id)
    except Exception as e:
        logger.warning(f"Failed to delete embeddings for {contract_id}: {e}")
        return 0
