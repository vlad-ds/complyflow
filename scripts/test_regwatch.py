"""
Test script for regwatch EUR-Lex connector.

Fetches documents from DORA and AIFMD feeds, with full text via Jina.ai.

Usage:
    PYTHONPATH=src uv run python scripts/test_regwatch.py
"""

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from regwatch.config import EURLEX_FEEDS
from regwatch.connectors.eurlex import EURLexConnector

# Configure logging to see connector activity
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

OUTPUT_DIR = Path("output/regwatch")


def json_serializer(obj):
    """Custom JSON serializer for dates and datetimes."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


async def test_feed(feed_name: str, limit: int = 10, fetch_full_text: bool = False):
    """Test fetching from a specific feed."""
    # Find the feed by name/topic
    feed = next((f for f in EURLEX_FEEDS if feed_name.upper() in f.topic.upper()), None)
    if not feed:
        print(f"Feed not found: {feed_name}")
        return []

    print(f"\n{'='*60}")
    print(f"FEED: {feed.name}")
    print(f"Topic: {feed.topic}")
    print(f"Source: {feed.source_doc}")
    print(f"URL: {feed.url[:80]}...")
    print(f"Fetch full text: {fetch_full_text}")
    print(f"{'='*60}\n")

    connector = EURLexConnector(feed)

    try:
        # Fetch without date filter to get all available items
        documents = await connector.fetch_all(limit=limit, fetch_full_text=fetch_full_text)

        if not documents:
            print("No documents found in feed.")
            return []

        print(f"Found {len(documents)} documents:\n")

        for i, doc in enumerate(documents, 1):
            print(f"{i}. {doc.title[:80]}{'...' if len(doc.title) > 80 else ''}")
            print(f"   Date: {doc.publication_date or 'N/A'}")
            print(f"   Type: {doc.doc_type}")
            print(f"   CELEX: {doc.doc_id or 'N/A'}")
            print(f"   URL: {doc.url[:70]}...")
            if fetch_full_text and doc.content:
                print(f"   Content length: {len(doc.content)} chars")
                preview = doc.content[:200].replace("\n", " ")
                print(f"   Preview: {preview}...")
            elif doc.summary:
                summary = doc.summary[:150].replace("\n", " ")
                print(f"   Summary: {summary}...")
            print()

        # Save to JSON
        output_file = OUTPUT_DIR / f"{feed.topic.lower()}_documents.json"
        docs_as_dicts = [asdict(doc) for doc in documents]
        with open(output_file, "w") as f:
            json.dump(docs_as_dicts, f, indent=2, default=json_serializer)
        print(f"Saved to: {output_file}")

        return documents

    finally:
        await connector.close()


async def main():
    """Test DORA and AIFMD feeds with full text fetching."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("REGWATCH - EUR-Lex RSS Feed Test (with full text)")
    print("=" * 60)

    # Test DORA feed - fetch 10 documents with full text
    dora_docs = await test_feed("DORA", limit=10, fetch_full_text=True)

    # Test AIFMD feed - fetch 10 documents with full text
    aifmd_docs = await test_feed("AIFMD", limit=10, fetch_full_text=True)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"DORA documents:  {len(dora_docs)}")
    print(f"AIFMD documents: {len(aifmd_docs)}")
    print(f"Total:           {len(dora_docs) + len(aifmd_docs)}")

    # Show content stats
    for docs, name in [(dora_docs, "DORA"), (aifmd_docs, "AIFMD")]:
        total_chars = sum(len(d.content) for d in docs if d.content)
        print(f"{name} total content: {total_chars:,} chars")


if __name__ == "__main__":
    asyncio.run(main())
