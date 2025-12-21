"""
Qdrant client wrapper for regwatch.

Provides incremental upsert with deterministic point IDs for idempotent operations.
"""

import hashlib
import logging
import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from regwatch.embeddings import EMBEDDING_DIM
from regwatch.ingest_config import IngestConfig

load_dotenv()

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


def _make_point_id(celex: str, chunk_index: int) -> int:
    """
    Create a deterministic point ID from CELEX and chunk index.

    Uses hash to create a stable integer ID. This makes upserts idempotent -
    re-uploading the same chunk will overwrite, not duplicate.

    Args:
        celex: Document CELEX number
        chunk_index: Chunk position in document

    Returns:
        Positive integer suitable for Qdrant point ID
    """
    # Create a stable string key
    key = f"{celex}_chunk_{chunk_index}"
    # Hash to get consistent integer (use first 16 hex chars = 64 bits)
    hash_hex = hashlib.sha256(key.encode()).hexdigest()[:16]
    # Convert to positive integer
    return int(hash_hex, 16)


class RegwatchQdrant:
    """
    Qdrant client with incremental upsert support.

    Features:
    - Deterministic point IDs for idempotent uploads
    - Deduplication check by CELEX
    - Batched upserts for efficiency
    """

    def __init__(self, config: IngestConfig):
        self.config = config
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        """Lazy-initialize Qdrant client."""
        if self._client is None:
            if not QDRANT_URL or not QDRANT_API_KEY:
                raise ValueError("QDRANT_URL and QDRANT_API_KEY must be set")
            self._client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            logger.info(f"Connected to Qdrant: {QDRANT_URL}")
        return self._client

    def ensure_collection_exists(self) -> None:
        """Create collection and indexes if they don't exist."""
        collections = [c.name for c in self.client.get_collections().collections]

        if self.config.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.config.collection_name,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
            logger.info(f"Created collection: {self.config.collection_name}")
        else:
            logger.debug(f"Collection exists: {self.config.collection_name}")

        # Ensure keyword index on doc_id for filtering
        self._ensure_payload_index("doc_id", PayloadSchemaType.KEYWORD)

    def _ensure_payload_index(self, field_name: str, schema_type: PayloadSchemaType) -> None:
        """Create payload index if it doesn't exist."""
        try:
            self.client.create_payload_index(
                collection_name=self.config.collection_name,
                field_name=field_name,
                field_schema=schema_type,
            )
            logger.info(f"Created index on {field_name}")
        except Exception as e:
            # Index might already exist, which is fine
            if "already exists" in str(e).lower():
                logger.debug(f"Index on {field_name} already exists")
            else:
                logger.warning(f"Failed to create index on {field_name}: {e}")

    def is_indexed(self, celex: str) -> bool:
        """
        Check if a document is already indexed in Qdrant.

        Args:
            celex: Document CELEX number

        Returns:
            True if any chunks exist for this CELEX
        """
        result = self.client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=celex))]
            ),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return len(result[0]) > 0

    def upsert_chunks(
        self,
        celex: str,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> int:
        """
        Upsert chunks to Qdrant with deterministic point IDs.

        Args:
            celex: Document CELEX number (used for point ID generation)
            chunks: List of chunk dicts with metadata
            embeddings: List of embedding vectors (same order as chunks)

        Returns:
            Number of points upserted
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"Chunk/embedding count mismatch: {len(chunks)} vs {len(embeddings)}"
            )

        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = _make_point_id(celex, chunk["chunk_index"])
            # Use chunk dict as payload (all metadata already present)
            payload = {k: v for k, v in chunk.items()}

            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            )

        # Upsert in batches
        batch_size = self.config.upsert_batch_size
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            self.client.upsert(
                collection_name=self.config.collection_name,
                points=batch,
            )

        logger.debug(f"Upserted {len(points)} points for {celex}")
        return len(points)

    def get_collection_stats(self) -> dict:
        """Get collection statistics."""
        try:
            info = self.client.get_collection(self.config.collection_name)
            return {
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status.value,
            }
        except Exception as e:
            logger.warning(f"Failed to get collection stats: {e}")
            return {"error": str(e)}

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 20,
        score_threshold: float = 0.4,
    ) -> list[dict]:
        """
        Search for similar chunks using vector similarity.

        Args:
            query_embedding: Query vector (768-dim for Snowflake Arctic)
            top_k: Number of results to return
            score_threshold: Minimum similarity score (0-1). Default 0.4 tuned
                for Snowflake Arctic which produces scores in 0.5-0.65 range
                for relevant content.

        Returns:
            List of chunk dicts with doc_id, title, text, topic, score
        """
        # Use query_points (new qdrant-client API) instead of deprecated search
        response = self.client.query_points(
            collection_name=self.config.collection_name,
            query=query_embedding,
            limit=top_k,
            with_payload=True,
            score_threshold=score_threshold,
        )
        return [
            {
                "doc_id": point.payload.get("doc_id"),
                "title": point.payload.get("title"),
                "text": point.payload.get("text"),
                "topic": point.payload.get("topic"),
                "chunk_index": point.payload.get("chunk_index"),
                "score": point.score,
            }
            for point in response.points
        ]
