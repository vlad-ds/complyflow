"""
Document chunking for regulatory documents.

Splits documents into chunks suitable for embedding and retrieval.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from regwatch.ingest_config import IngestConfig
from regwatch.metadata import DocumentMetadata


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

    Args:
        content: Full document text
        metadata: Extracted document metadata
        source_file: Source file path (e.g., "DORA/32022R2554.txt")
        config: Ingestion configuration

    Returns:
        List of chunk dicts with:
        - text: The chunk text
        - chunk_index: Position in document
        - All metadata fields for Qdrant payload
    """
    splitter = create_splitter(config)
    splits = splitter.split_text(content)

    chunks = []
    for i, chunk_text in enumerate(splits):
        # Get chunk metadata from document metadata
        chunk_meta = metadata.to_chunk_metadata(
            chunk_index=i,
            source_file=source_file,
        )
        chunk_meta["text"] = chunk_text

        chunks.append(chunk_meta)

    return chunks
