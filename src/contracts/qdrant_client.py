"""
Qdrant client wrapper for contracts collection.

Provides upsert with deterministic point IDs for idempotent operations.
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

from contracts.config import ContractEmbedConfig
from regwatch.embeddings import EMBEDDING_DIM

load_dotenv()

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


def _make_point_id(contract_id: str, chunk_index: int) -> int:
    """
    Create a deterministic point ID from contract ID and chunk index.

    Uses hash to create a stable integer ID. This makes upserts idempotent -
    re-uploading the same chunk will overwrite, not duplicate.

    Args:
        contract_id: Airtable record ID
        chunk_index: Chunk position in document

    Returns:
        Positive integer suitable for Qdrant point ID
    """
    key = f"{contract_id}_chunk_{chunk_index}"
    hash_hex = hashlib.sha256(key.encode()).hexdigest()[:16]
    return int(hash_hex, 16)


class ContractsQdrant:
    """
    Qdrant client for contracts collection.

    Features:
    - Deterministic point IDs for idempotent uploads
    - Deduplication check by contract_id
    - Batched upserts for efficiency
    """

    def __init__(self, config: ContractEmbedConfig | None = None):
        self.config = config or ContractEmbedConfig()
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

        # Ensure keyword index on contract_id for filtering
        self._ensure_payload_index("contract_id", PayloadSchemaType.KEYWORD)

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
            if "already exists" in str(e).lower():
                logger.debug(f"Index on {field_name} already exists")
            else:
                logger.warning(f"Failed to create index on {field_name}: {e}")

    def is_indexed(self, contract_id: str) -> bool:
        """
        Check if a contract is already indexed in Qdrant.

        Args:
            contract_id: Airtable record ID

        Returns:
            True if any chunks exist for this contract
        """
        result = self.client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="contract_id", match=MatchValue(value=contract_id))]
            ),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
        return len(result[0]) > 0

    def delete_contract(self, contract_id: str) -> int:
        """
        Delete all chunks for a contract from Qdrant.

        Args:
            contract_id: Airtable record ID

        Returns:
            Number of points deleted
        """
        # First count how many points exist
        result = self.client.scroll(
            collection_name=self.config.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="contract_id", match=MatchValue(value=contract_id))]
            ),
            limit=1000,
            with_payload=False,
            with_vectors=False,
        )
        count = len(result[0])

        if count > 0:
            self.client.delete(
                collection_name=self.config.collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="contract_id", match=MatchValue(value=contract_id))]
                ),
            )
            logger.info(f"Deleted {count} points for contract {contract_id}")

        return count

    def upsert_chunks(
        self,
        contract_id: str,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> int:
        """
        Upsert chunks to Qdrant with deterministic point IDs.

        Args:
            contract_id: Airtable record ID (used for point ID generation)
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
        for chunk, embedding in zip(chunks, embeddings):
            point_id = _make_point_id(contract_id, chunk["chunk_index"])
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

        logger.info(f"Upserted {len(points)} points for contract {contract_id}")
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
        contract_id: str | None = None,
        score_threshold: float = 0.7,
    ) -> list[dict]:
        """
        Search for similar chunks using vector similarity.

        Args:
            query_embedding: Query vector (768-dim for Snowflake Arctic)
            top_k: Number of results to return
            contract_id: Optional filter to search within a specific contract
            score_threshold: Minimum similarity score (0-1). Default 0.7 filters
                out low-relevance chunks. Not empirically validated - chosen as
                sensible default for cosine similarity.

        Returns:
            List of chunk dicts with contract_id, filename, text, score
        """
        search_filter = None
        if contract_id:
            search_filter = Filter(
                must=[FieldCondition(key="contract_id", match=MatchValue(value=contract_id))]
            )

        response = self.client.query_points(
            collection_name=self.config.collection_name,
            query=query_embedding,
            query_filter=search_filter,
            limit=top_k,
            with_payload=True,
            score_threshold=score_threshold,
        )

        return [
            {
                "contract_id": point.payload.get("contract_id"),
                "filename": point.payload.get("filename"),
                "contract_type": point.payload.get("contract_type"),
                "parties": point.payload.get("parties"),
                "text": point.payload.get("text"),
                "chunk_index": point.payload.get("chunk_index"),
                "score": point.score,
            }
            for point in response.points
        ]
