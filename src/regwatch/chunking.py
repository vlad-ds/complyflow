"""
Document chunking for regulatory documents.

Splits documents into chunks suitable for embedding and retrieval.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from regwatch.ingest_config import IngestConfig
from regwatch.metadata import DocumentMetadata


def format_metadata_header(metadata: DocumentMetadata) -> str:
    """
    Format metadata as a searchable header to prepend to chunk text.

    This enables semantic search to find documents by their identifiers
    (CELEX, title, topic) - not just by content similarity.

    Args:
        metadata: Document metadata with CELEX, title, topic, etc.

    Returns:
        Formatted header string like:
        "[CELEX: 32022R2554 | Topic: DORA | Type: regulation]
        Title: Digital Operational Resilience Act (DORA)
        ---"
    """
    parts = []

    # Primary identifier line with bracketed metadata
    id_parts = []
    if metadata.celex:
        id_parts.append(f"CELEX: {metadata.celex}")
    if metadata.topic:
        id_parts.append(f"Topic: {metadata.topic}")
    if metadata.doc_type:
        id_parts.append(f"Type: {metadata.doc_type}")

    if id_parts:
        parts.append(f"[{' | '.join(id_parts)}]")

    # Title on separate line for better readability
    if metadata.title:
        parts.append(f"Title: {metadata.title}")

    # Short subject if available and different from title
    if metadata.short_subject and metadata.short_subject != metadata.title:
        parts.append(f"Subject: {metadata.short_subject}")

    if parts:
        parts.append("---")
        return "\n".join(parts) + "\n"

    return ""


def create_splitter(config: IngestConfig) -> RecursiveCharacterTextSplitter:
    """Create a text splitter with the given configuration."""
    return RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_document(
    content: str,
    metadata: DocumentMetadata,
    source_file: str,
    config: IngestConfig,
) -> list[dict]:
    """
    Split a document into chunks with metadata payload.

    Each chunk's text is prepended with a metadata header containing the CELEX
    identifier, topic, and title. This enables semantic search to find documents
    by their identifiers (e.g., "CELEX 32022R2554" or "DORA regulation").

    Args:
        content: Full document text
        metadata: Extracted document metadata
        source_file: Source file path (e.g., "DORA/32022R2554.txt")
        config: Ingestion configuration

    Returns:
        List of chunk dicts with:
        - text: The chunk text (with metadata header prepended)
        - chunk_index: Position in document
        - All metadata fields for Qdrant payload
    """
    splitter = create_splitter(config)
    splits = splitter.split_text(content)

    # Create metadata header once (same for all chunks)
    metadata_header = format_metadata_header(metadata)

    chunks = []
    for i, chunk_text in enumerate(splits):
        # Get chunk metadata from document metadata
        chunk_meta = metadata.to_chunk_metadata(
            chunk_index=i,
            source_file=source_file,
        )
        # Prepend metadata header so semantic search can find by CELEX/topic/title
        chunk_meta["text"] = metadata_header + chunk_text

        chunks.append(chunk_meta)

    return chunks
