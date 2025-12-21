# ComplyFlow TODOs

Technical debt and planned improvements.

## Regwatch Document Registry Enhancement

**Problem**: Document metadata (title, URL, doc_type) is not persisted in the registry. Currently:
- Title comes from RSS feed (ephemeral)
- Text files in S3 store raw content only
- Qdrant chunks have title in payload, but that's derived data
- Registry only stores: celex, topic, indexed_at, chunk_count

**Impact**: To list documents with titles, we have to query Qdrant (slow, wrong source of truth).

**Solution**: Enhance `IndexedDocument` in `src/regwatch/registry.py`:

```python
@dataclass
class IndexedDocument:
    celex: str
    topic: str
    indexed_at: str
    chunk_count: int
    # Add these:
    title: str | None = None
    url: str | None = None
    doc_type: str | None = None
```

Then update `mark_indexed()` call in `ingest.py` to pass these fields.

**Temporary workaround**: `/regwatch/documents` endpoint queries Qdrant for titles. This works but is slower and uses derived data as source of truth.
