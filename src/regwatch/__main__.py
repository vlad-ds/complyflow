"""
CLI entry point for regwatch ingestion.

Usage:
    PYTHONPATH=src python -m regwatch.ingest
    PYTHONPATH=src python -m regwatch.ingest --dry-run
    PYTHONPATH=src python -m regwatch.ingest --recent-docs-limit 10 --verbose
"""

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

from regwatch.ingest import run_ingestion
from regwatch.ingest_config import IngestConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """CLI entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Ingest regulatory documents from RSS feeds to Qdrant"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and process documents but don't upload to Qdrant",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress",
    )
    parser.add_argument(
        "--recent-docs-limit",
        type=int,
        default=None,
        help="Number of recent documents to fetch per feed (default: 5)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=None,
        help="Only fetch documents from last N days (default: 30)",
    )
    parser.add_argument(
        "--feeds",
        type=str,
        default="DORA,MiCA",
        help="Comma-separated list of feeds to process (default: DORA,MiCA)",
    )

    args = parser.parse_args()

    # Build config from CLI args (use defaults from IngestConfig if not specified)
    config_kwargs = {
        "feeds": args.feeds.split(","),
        "dry_run": args.dry_run,
        "verbose": args.verbose,
    }
    if args.recent_docs_limit is not None:
        config_kwargs["recent_docs_limit"] = args.recent_docs_limit
    if args.lookback_days is not None:
        config_kwargs["lookback_days"] = args.lookback_days

    config = IngestConfig(**config_kwargs)

    if args.verbose:
        logging.getLogger("regwatch").setLevel(logging.DEBUG)

    # Print banner
    print("=" * 60)
    print("REGWATCH - Daily Document Ingestion")
    print("=" * 60)
    print(f"Feeds: {config.feeds}")
    print(f"Recent docs limit: {config.recent_docs_limit}")
    print(f"Lookback days: {config.lookback_days}")
    print(f"Dry run: {config.dry_run}")
    print("=" * 60)

    # Run ingestion
    result = asyncio.run(run_ingestion(config))

    # Print results
    print("\n" + "=" * 60)
    print("INGESTION COMPLETE")
    print("=" * 60)
    print(result.summary())

    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    # Exit with error code if there were failures
    if result.errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
