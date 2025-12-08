"""
Configuration for contract embedding pipeline.

Mirrors regwatch settings for consistency.
"""

from dataclasses import dataclass


@dataclass
class ContractEmbedConfig:
    """Configuration for contract embedding pipeline."""

    # Chunking Settings (same as regwatch)
    chunk_size: int = 2048  # Characters per chunk (matches embedding model window)
    chunk_overlap: int = 200  # Overlap between chunks for context continuity

    # Embedding Settings
    embedding_batch_size: int = 16  # Chunks per embedding batch (conservative for memory)

    # Qdrant Settings
    collection_name: str = "contracts"
    upsert_batch_size: int = 32  # Points per upsert batch

    def __post_init__(self):
        """Validate configuration."""
        if self.chunk_size < 100:
            raise ValueError("chunk_size must be at least 100")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
