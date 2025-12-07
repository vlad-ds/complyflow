"""
Quick test of Cellar API full text fetching.

Usage:
    PYTHONPATH=src uv run python scripts/test_cellar.py
"""

import asyncio

from regwatch.config import EURLEX_FEEDS
from regwatch.connectors.eurlex import EURLexConnector


async def main():
    """Test fetching the main DORA regulation."""
    feed = next(f for f in EURLEX_FEEDS if f.topic == "DORA")
    connector = EURLexConnector(feed)

    try:
        # Fetch the main DORA regulation (known to exist in Cellar)
        celex = "32022R2554"
        print(f"Fetching {celex} from Cellar API...")

        full_text = await connector.fetch_full_text(celex)

        if full_text:
            print(f"\nSuccess! Got {len(full_text):,} characters")
            print(f"\nFirst 1000 characters:\n{'='*60}")
            print(full_text[:1000])
            print(f"{'='*60}")

            # Save to file for inspection
            with open("output/regwatch/dora_full_text.txt", "w") as f:
                f.write(full_text)
            print(f"\nFull text saved to: output/regwatch/dora_full_text.txt")
        else:
            print("Failed to fetch document")

    finally:
        await connector.close()


if __name__ == "__main__":
    asyncio.run(main())
