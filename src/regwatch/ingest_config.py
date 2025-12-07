"""
Configuration for daily document ingestion pipeline.

All free parameters in one place for easy tuning.
"""

from dataclasses import dataclass, field


@dataclass
class IngestConfig:
    """Configuration for daily ingestion pipeline."""

    # RSS Feed Settings
    feeds: list[str] = field(default_factory=lambda: ["DORA", "MiCA"])
    recent_docs_limit: int = 5  # How many recent docs to fetch per feed
    lookback_days: int = 30  # Only fetch docs published in last N days (RSS dates vary)

    # Chunking Settings
    chunk_size: int = 2048  # Characters per chunk (matches embedding model window)
    chunk_overlap: int = 200  # Overlap between chunks for context continuity

    # Embedding Settings
    embedding_batch_size: int = 32  # Chunks per embedding batch

    # Qdrant Settings
    collection_name: str = "regwatch"
    upsert_batch_size: int = 32  # Points per upsert batch

    # Registry Settings
    registry_filename: str = "indexed_documents.json"

    # Runtime Settings
    dry_run: bool = False  # If True, fetch and process but don't upload to Qdrant
    verbose: bool = False  # If True, print detailed progress

    def __post_init__(self):
        """Validate configuration."""
        if self.recent_docs_limit < 1:
            raise ValueError("recent_docs_limit must be at least 1")
        if self.chunk_size < 100:
            raise ValueError("chunk_size must be at least 100")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
