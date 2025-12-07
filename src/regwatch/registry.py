"""
Registry for tracking indexed documents.

Stores which documents have been successfully indexed to Qdrant,
with timestamps and chunk counts. Persists to S3 (Railway) or local file.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime

from regwatch.storage import get_storage

logger = logging.getLogger(__name__)

# Registry is stored at the root of the regwatch cache, not in a subfolder
REGISTRY_SUBFOLDER = None


@dataclass
class IndexedDocument:
    """Record of a document that has been indexed to Qdrant."""

    celex: str
    topic: str
    indexed_at: str  # ISO format datetime
    chunk_count: int

    @classmethod
    def create(cls, celex: str, topic: str, chunk_count: int) -> "IndexedDocument":
        """Create a new indexed document record with current timestamp."""
        return cls(
            celex=celex,
            topic=topic,
            indexed_at=datetime.utcnow().isoformat(),
            chunk_count=chunk_count,
        )


class DocumentRegistry:
    """
    Track indexed documents in S3/local JSON file.

    The registry is the source of truth for which documents have been
    successfully indexed. A document is only added after ALL chunks
    are successfully uploaded to Qdrant.
    """

    def __init__(self, filename: str = "indexed_documents.json"):
        self.filename = filename
        self._documents: dict[str, IndexedDocument] = {}
        self._dirty = False

    def load(self) -> None:
        """Load registry from storage."""
        storage = get_storage()
        # Remove .json extension for storage key (storage adds .txt)
        key = self.filename.replace(".json", "")
        content = storage.read(key, subfolder=REGISTRY_SUBFOLDER)

        if content:
            try:
                data = json.loads(content)
                self._documents = {
                    celex: IndexedDocument(**doc) for celex, doc in data.items()
                }
                logger.info(f"Loaded registry with {len(self._documents)} documents")
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse registry, starting fresh: {e}")
                self._documents = {}
        else:
            logger.info("No existing registry found, starting fresh")
            self._documents = {}

        self._dirty = False

    def save(self) -> None:
        """Save registry to storage."""
        if not self._dirty:
            logger.debug("Registry not modified, skipping save")
            return

        storage = get_storage()
        key = self.filename.replace(".json", "")
        content = json.dumps(
            {celex: asdict(doc) for celex, doc in self._documents.items()},
            indent=2,
        )
        storage.write(key, content, subfolder=REGISTRY_SUBFOLDER)
        logger.info(f"Saved registry with {len(self._documents)} documents")
        self._dirty = False

    def is_indexed(self, celex: str) -> bool:
        """Check if a document has been indexed."""
        return celex in self._documents

    def mark_indexed(self, celex: str, topic: str, chunk_count: int) -> None:
        """Mark a document as successfully indexed."""
        self._documents[celex] = IndexedDocument.create(celex, topic, chunk_count)
        self._dirty = True
        logger.debug(f"Marked {celex} as indexed ({chunk_count} chunks)")

    def get_indexed_count(self) -> int:
        """Return total number of indexed documents."""
        return len(self._documents)

    def get_all_indexed(self) -> list[IndexedDocument]:
        """Return all indexed documents."""
        return list(self._documents.values())
