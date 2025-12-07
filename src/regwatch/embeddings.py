"""
Embedding utilities for regulatory document retrieval.

Uses Snowflake Arctic Embed M Long - optimized for:
- Retrieval tasks (MTEB score: 57.02)
- Low memory footprint (~522MB)
- 2048 token context window (matches our chunking strategy)
"""

from dataclasses import dataclass
from typing import Iterator

from fastembed import TextEmbedding

# Model selection rationale:
# - Snowflake Arctic M Long: Best retrieval score among lightweight models
# - 2048 token context: No truncation of our 2048-char chunks
# - 522MB RAM: Fits Railway free tier (512MB-1GB)
MODEL_NAME = "snowflake/snowflake-arctic-embed-m-long"
EMBEDDING_DIM = 768  # Arctic M Long produces 768-dim vectors

# Query prefix required for Arctic Embed models (v1.x)
# See: https://huggingface.co/Snowflake/snowflake-arctic-embed-m-long
# Documents don't need a prefix, only queries
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@dataclass
class EmbeddingConfig:
    """Configuration for the embedding model."""

    model_name: str = MODEL_NAME
    batch_size: int = 32  # Process chunks in batches
    max_length: int = 2048  # Token limit (matches chunk size)


@dataclass
class RetrievalConfig:
    """Configuration for retrieval/search."""

    top_k: int = 20  # Number of chunks to retrieve (20 gives 100% recall on golden dataset)
    collection_name: str = "regwatch"


class DocumentEmbedder:
    """
    Embeds text chunks using Snowflake Arctic Embed M Long.

    Usage:
        embedder = DocumentEmbedder()
        vectors = embedder.embed_texts(["chunk 1", "chunk 2", ...])
        query_vector = embedder.embed_query("What is DORA?")
    """

    def __init__(self, config: EmbeddingConfig | None = None):
        self.config = config or EmbeddingConfig()
        self._model: TextEmbedding | None = None

    @property
    def model(self) -> TextEmbedding:
        """Lazy-load the embedding model."""
        if self._model is None:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Loading embedding model: {self.config.model_name}")
            try:
                self._model = TextEmbedding(
                    model_name=self.config.model_name,
                    max_length=self.config.max_length,
                )
                logger.info("Embedding model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load embedding model: {type(e).__name__}: {e}")
                raise
        return self._model

    @property
    def dimension(self) -> int:
        """Return embedding dimension for vector store configuration."""
        return EMBEDDING_DIM

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of text chunks for indexing.

        Args:
            texts: List of text chunks to embed

        Returns:
            List of embedding vectors (each is a list of floats)
        """
        if not texts:
            return []

        # FastEmbed returns a generator, convert to list
        embeddings = list(self.model.embed(texts))

        # Convert numpy arrays to lists for JSON serialization
        return [emb.tolist() for emb in embeddings]

    def embed_texts_batched(
        self, texts: list[str], batch_size: int | None = None
    ) -> Iterator[list[list[float]]]:
        """
        Embed texts in batches (memory-efficient for large document sets).

        Args:
            texts: List of text chunks to embed
            batch_size: Override default batch size

        Yields:
            Batches of embedding vectors
        """
        batch_size = batch_size or self.config.batch_size

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            yield self.embed_texts(batch)

    def embed_query(self, query: str) -> list[float]:
        """
        Embed a single query for retrieval.

        Arctic Embed models require a specific prefix for queries to activate
        retrieval capabilities. Documents don't need prefixes.

        Args:
            query: The search query

        Returns:
            Query embedding vector
        """
        # Add query prefix for Arctic Embed models
        prefixed_query = f"{QUERY_PREFIX}{query}"
        embeddings = list(self.model.embed([prefixed_query]))

        return embeddings[0].tolist()


# Singleton instance for convenience
_embedder: DocumentEmbedder | None = None


def get_embedder() -> DocumentEmbedder:
    """Get or create the singleton embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = DocumentEmbedder()
    return _embedder


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Add embeddings to a list of chunks.

    Args:
        chunks: List of chunk dicts with 'text' key

    Returns:
        Same chunks with 'embedding' key added
    """
    embedder = get_embedder()
    texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_texts(texts)

    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding

    return chunks
