"""
Daily document ingestion pipeline.

Fetches new regulatory documents from RSS feeds, chunks them,
generates embeddings, and uploads to Qdrant.

Registry (stored in S3) is the source of truth for fully-indexed documents.
A document is only added to registry AFTER all chunks are uploaded to Qdrant.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from regwatch.chunking import chunk_document
from regwatch.config import EURLEX_FEEDS
from regwatch.connectors.eurlex import EURLexConnector
from regwatch.embeddings import get_embedder
from regwatch.ingest_config import IngestConfig
from regwatch.materiality import analyze_and_notify
from regwatch.metadata import extract_metadata
from regwatch.qdrant_client import RegwatchQdrant
from regwatch.registry import DocumentRegistry

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Summary of ingestion run."""

    feeds_checked: int = 0
    documents_found: int = 0
    documents_skipped: int = 0  # Already indexed
    documents_indexed: int = 0
    chunks_created: int = 0
    material_documents: int = 0  # Documents flagged as material
    slack_notifications_sent: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def summary(self) -> str:
        """Return human-readable summary."""
        lines = [
            f"Feeds checked: {self.feeds_checked}",
            f"Documents found: {self.documents_found}",
            f"Documents skipped (already indexed): {self.documents_skipped}",
            f"Documents indexed: {self.documents_indexed}",
            f"Chunks created: {self.chunks_created}",
            f"Material documents: {self.material_documents}",
            f"Slack notifications sent: {self.slack_notifications_sent}",
            f"Errors: {len(self.errors)}",
            f"Duration: {self.duration_seconds:.1f}s",
        ]
        return "\n".join(lines)


async def run_ingestion(config: IngestConfig) -> IngestResult:
    """
    Run the daily ingestion pipeline.

    Steps:
    1. Load registry of indexed documents
    2. For each feed: fetch recent documents
    3. For each new document:
       - Fetch full text (cached)
       - Extract metadata
       - Chunk
       - Embed
       - Upsert to Qdrant
       - Mark as indexed
    4. Save registry
    5. Return summary

    Args:
        config: Ingestion configuration

    Returns:
        IngestResult with summary statistics
    """
    start_time = time.time()
    result = IngestResult()

    # Initialize components
    registry = DocumentRegistry(config.registry_filename)
    registry.load()

    qdrant = RegwatchQdrant(config)
    embedder = get_embedder()

    # Ensure Qdrant collection exists (unless dry run)
    if not config.dry_run:
        qdrant.ensure_collection_exists()

    # Get feeds to process
    feeds_to_process = [
        feed for feed in EURLEX_FEEDS if feed.topic in config.feeds
    ]
    result.feeds_checked = len(feeds_to_process)

    if config.verbose:
        logger.info(f"Processing {len(feeds_to_process)} feeds: {config.feeds}")

    # Process each feed
    for feed in feeds_to_process:
        try:
            await _process_feed(
                feed=feed,
                config=config,
                registry=registry,
                qdrant=qdrant,
                embedder=embedder,
                result=result,
            )
        except Exception as e:
            error_msg = f"Feed {feed.topic} failed: {type(e).__name__}: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)

    # Save registry (unless dry run)
    if not config.dry_run:
        registry.save()

    result.duration_seconds = time.time() - start_time
    return result


async def _process_feed(
    feed,
    config: IngestConfig,
    registry: DocumentRegistry,
    qdrant: RegwatchQdrant,
    embedder,
    result: IngestResult,
) -> None:
    """Process a single RSS feed."""
    logger.info(f"Processing feed: {feed.topic}")

    connector = EURLexConnector(feed)
    try:
        # Fetch recent documents
        documents = await connector.fetch_recent(
            days=config.lookback_days,
            limit=config.recent_docs_limit,
        )

        if config.verbose:
            logger.info(f"Found {len(documents)} documents in {feed.topic}")

        result.documents_found += len(documents)

        # Process each document
        for doc in documents:
            if not doc.doc_id:
                logger.warning(f"Document without CELEX: {doc.title[:50]}")
                continue

            celex = doc.doc_id

            # Check registry - this is the source of truth for fully-indexed documents
            # We don't check Qdrant because partial uploads (from failures) would give false positives
            if registry.is_indexed(celex):
                if config.verbose:
                    logger.debug(f"Skipping {celex} (in registry)")
                result.documents_skipped += 1
                continue

            # Fetch full text
            try:
                full_text = await connector.fetch_full_text(celex)
                if not full_text:
                    logger.warning(f"Failed to fetch full text for {celex}")
                    result.errors.append(f"No content: {celex}")
                    continue
            except Exception as e:
                logger.warning(f"Error fetching {celex}: {e}")
                result.errors.append(f"Fetch error {celex}: {e}")
                continue

            # Extract metadata
            metadata = extract_metadata(
                celex=celex,
                content=full_text,
                topic=feed.topic,
                publication_date=doc.publication_date,
                title=doc.title,
                url=doc.url,
            )

            # Chunk document
            source_file = f"{feed.topic}/{celex}.txt"
            chunks = chunk_document(full_text, metadata, source_file, config)

            if config.verbose:
                logger.info(f"Created {len(chunks)} chunks for {celex}")

            if config.dry_run:
                logger.info(f"[DRY RUN] Would index {celex} ({len(chunks)} chunks)")
                result.documents_indexed += 1
                result.chunks_created += len(chunks)
                continue

            # Generate embeddings in batches to avoid OOM
            logger.info(f"Starting embedding for {len(chunks)} chunks...")
            texts = [c["text"] for c in chunks]
            try:
                embeddings = []
                batch_size = 16  # Small batches to avoid OOM
                for i in range(0, len(texts), batch_size):
                    batch = texts[i:i + batch_size]
                    batch_num = i // batch_size + 1
                    total_batches = (len(texts) + batch_size - 1) // batch_size
                    logger.info(f"Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)...")
                    batch_embeddings = embedder.embed_texts(batch)
                    embeddings.extend(batch_embeddings)
                    logger.info(f"Batch {batch_num} complete")
                logger.info(f"Embedding complete: {len(embeddings)} vectors")
            except Exception as e:
                logger.error(f"Embedding failed: {type(e).__name__}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                result.errors.append(f"Embedding error {celex}: {e}")
                continue

            # Upsert to Qdrant
            try:
                qdrant.upsert_chunks(celex, chunks, embeddings)
            except Exception as e:
                logger.error(f"Failed to upsert {celex}: {e}")
                result.errors.append(f"Upsert error {celex}: {e}")
                continue

            # Mark as indexed (only after successful upsert)
            registry.mark_indexed(celex, feed.topic, len(chunks))
            result.documents_indexed += 1
            result.chunks_created += len(chunks)

            logger.info(f"Indexed {celex}: {len(chunks)} chunks")

            # Analyze materiality and send Slack notification if material
            # This happens AFTER indexing to ensure we don't notify for failed documents
            if not config.dry_run:
                try:
                    materiality_result = await analyze_and_notify(
                        celex=celex,
                        topic=feed.topic,
                        title=doc.title,
                        content=full_text,
                    )
                    if materiality_result.is_material:
                        result.material_documents += 1
                        if materiality_result.slack_notified:
                            result.slack_notifications_sent += 1
                        logger.info(
                            f"Material document {celex}: {materiality_result.relevance} relevance"
                        )
                except Exception as e:
                    # Don't fail ingestion if materiality analysis fails
                    logger.warning(f"Materiality analysis failed for {celex}: {e}")

    finally:
        await connector.close()
