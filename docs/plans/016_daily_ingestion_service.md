# Plan: Daily Regulatory Document Ingestion Service

## Overview

Build a scheduled Railway service that runs daily to:
1. Query DORA and MiCA RSS feeds for recent documents
2. Skip documents already indexed in Qdrant (deduplication)
3. Fetch full text via Jina.ai (cached in S3)
4. Chunk and embed documents
5. Upload to Qdrant vector store with deterministic point IDs

## Current State

### What Exists
- **EUR-Lex Connector** (`src/regwatch/connectors/eurlex.py`): Fetches RSS feeds, extracts full text via Jina.ai
- **Storage** (`src/regwatch/storage.py`): S3 on Railway, local in dev - caches fetched documents
- **Metadata** (`src/regwatch/metadata.py`): Pure regex parsing of CELEX numbers
- **Embeddings** (`src/regwatch/embeddings.py`): Snowflake Arctic Embed M Long (768-dim, 2048 tokens)
- **Index Script** (`scripts/index_regwatch.py`): Full re-index script (not incremental)
- **Railway Bucket**: `regwatch-5iiyfrzl-ffbnns5` with S3 credentials in `.env`
- **Deadline Alerts**: Existing cron job using same Docker image with different command

### Active Feeds (2 of 7)
| Feed | Topic | Documents |
|------|-------|-----------|
| DORA | DORA | 10 cached |
| MiCA | MiCA | 10 cached |

## Architecture

### Deployment Pattern
Follow the **Deadline Alerts** pattern:
- Same Docker image as main API
- Railway cron job with different start command
- Entry point: `python -m regwatch.ingest`

### Partial Failure Handling
Use **deterministic point IDs** for idempotent uploads:
```python
point_id = f"{celex}_chunk_{chunk_index}"  # e.g., "32022R2554_chunk_0"
```

- Qdrant `upsert` is idempotent - same ID = overwrite
- If job crashes mid-upload, restart re-uploads all chunks for that document
- Registry only marks document as "indexed" AFTER all chunks succeed
- No cleanup needed - just retry

### Deduplication
Query Qdrant to check if CELEX already indexed:
```python
existing = qdrant.scroll(
    collection_name="regwatch",
    scroll_filter=Filter(must=[FieldCondition(key="doc_id", match=MatchValue(value=celex))]),
    limit=1
)
```

## Configuration

All free parameters in one place: `src/regwatch/ingest_config.py`

```python
@dataclass
class IngestConfig:
    """Configuration for daily ingestion pipeline."""

    # RSS Feed Settings
    feeds: list[str] = field(default_factory=lambda: ["DORA", "MiCA"])
    recent_docs_limit: int = 5  # How many recent docs to fetch per feed
    lookback_days: int = 7      # Only fetch docs from last N days

    # Chunking Settings
    chunk_size: int = 2048
    chunk_overlap: int = 200

    # Embedding Settings
    embedding_batch_size: int = 32

    # Qdrant Settings
    collection_name: str = "regwatch"
    upsert_batch_size: int = 32

    # Runtime Settings
    dry_run: bool = False
    verbose: bool = False
```

## Implementation Plan

### 1. Configuration (`src/regwatch/ingest_config.py`)
- Dataclass with all free parameters
- Defaults that work out of the box
- CLI can override any setting

### 2. Registry Module (`src/regwatch/registry.py`)
```python
@dataclass
class IndexedDocument:
    celex: str
    topic: str
    indexed_at: datetime
    chunk_count: int

class DocumentRegistry:
    """Track indexed documents in S3/local JSON file."""

    def is_indexed(self, celex: str) -> bool
    def mark_indexed(self, celex: str, topic: str, chunk_count: int)
    def save()  # Persist to S3/local
    def load()  # Load from S3/local
```

### 3. Chunking Module (`src/regwatch/chunking.py`)
Extract from `index_regwatch.py`:
```python
def chunk_document(
    content: str,
    metadata: DocumentMetadata,
    config: IngestConfig
) -> list[dict]:
    """Split document into chunks with metadata payload."""
```

### 4. Qdrant Client (`src/regwatch/qdrant_client.py`)
```python
class RegwatchQdrant:
    """Qdrant client with incremental upsert support."""

    def is_indexed(self, celex: str) -> bool
    def upsert_chunks(self, celex: str, chunks: list[dict], embeddings: list[list[float]])
    def ensure_collection_exists()

    def _make_point_id(self, celex: str, chunk_index: int) -> str:
        """Deterministic ID: '{celex}_chunk_{index}'"""
```

### 5. Ingestion Module (`src/regwatch/ingest.py`)
Main orchestration:
```python
@dataclass
class IngestResult:
    feeds_checked: int
    documents_found: int
    documents_new: int
    documents_indexed: int
    chunks_created: int
    errors: list[str]
    duration_seconds: float

async def run_ingestion(config: IngestConfig) -> IngestResult:
    """
    Daily ingestion pipeline:
    1. Load registry
    2. For each feed in config.feeds:
       - Fetch recent documents (config.recent_docs_limit)
       - Filter out already-indexed (check Qdrant)
    3. For new documents:
       - Fetch full text (cached in S3)
       - Extract metadata
       - Chunk (config.chunk_size)
       - Embed
       - Upsert to Qdrant (deterministic IDs)
       - Mark as indexed in registry
    4. Save registry
    5. Return summary
    """
```

### 6. CLI Entry Point (`src/regwatch/__main__.py`)
```python
# PYTHONPATH=src python -m regwatch.ingest
# PYTHONPATH=src python -m regwatch.ingest --dry-run
# PYTHONPATH=src python -m regwatch.ingest --recent-docs-limit 10

parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--recent-docs-limit", type=int, default=5)
parser.add_argument("--verbose", action="store_true")
```

### 7. Railway Cron Job
In Railway dashboard, create cron job service:
- Schedule: `0 6 * * *` (daily at 6 AM UTC)
- Command: `python -m regwatch.ingest`
- Same env vars as main API

## File Structure

```
src/regwatch/
├── __init__.py
├── __main__.py          # CLI entry point (calls ingest.py)
├── ingest.py            # NEW: Main orchestration
├── ingest_config.py     # NEW: All free parameters
├── registry.py          # NEW: Track indexed documents
├── chunking.py          # NEW: Document chunking
├── qdrant_client.py     # NEW: Qdrant wrapper
├── config.py            # Existing: RSS feeds, Jina config
├── storage.py           # Existing: S3/local storage
├── embeddings.py        # Existing: Snowflake Arctic
├── metadata.py          # Existing: CELEX parsing
└── connectors/
    ├── base.py          # Existing
    └── eurlex.py        # Existing
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Feed fetch fails | Log error, continue to next feed |
| Jina.ai timeout | Retry 3x (existing logic), skip doc if fails |
| Qdrant unavailable | Fail entire run, exit code 1 |
| Partial chunk upload | Restart re-uploads all chunks (idempotent) |
| Embedding fails | Skip document, log error |

## Success Criteria

- [ ] Configuration file with all parameters
- [ ] Daily job runs and logs results
- [ ] Only new documents are processed
- [ ] Documents appear in Qdrant with correct metadata
- [ ] Partial failures don't corrupt state
- [ ] Dry run mode works for testing
