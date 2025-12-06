"""Base connector interface for regulatory sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


@dataclass
class Document:
    """A regulatory document fetched from a source."""

    # Required fields
    url: str  # Unique identifier - canonical URL
    title: str
    source: str  # e.g., "eurlex", "bafin", "esma"

    # Content
    content: str  # Full text content
    summary: str | None = None  # Short description if available

    # Metadata
    doc_type: str | None = None  # e.g., "regulation", "directive", "guidance"
    topics: list[str] = field(default_factory=list)  # e.g., ["DORA", "AML"]
    publication_date: date | None = None
    effective_date: date | None = None

    # Reference identifiers
    doc_id: str | None = None  # Source-specific ID (e.g., CELEX number)

    # Tracking
    fetched_at: datetime = field(default_factory=datetime.utcnow)


class BaseConnector(ABC):
    """Abstract base class for regulatory source connectors."""

    # Subclasses must define these
    source_id: str  # Short identifier, e.g., "eurlex"
    source_name: str  # Human-readable name, e.g., "EUR-Lex"

    @abstractmethod
    async def fetch_recent(self, days: int = 7) -> list[Document]:
        """
        Fetch documents published in the last N days.

        Args:
            days: Number of days to look back (default 7)

        Returns:
            List of Document objects
        """
        pass

    @abstractmethod
    async def fetch_document(self, url: str) -> Document | None:
        """
        Fetch a single document by URL.

        Args:
            url: Document URL

        Returns:
            Document object or None if not found
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if the source is reachable.

        Returns:
            True if healthy, False otherwise
        """
        # Default implementation - subclasses can override
        return True
