"""
Weekly digest cron service.

Generates a weekly summary from the materiality registry and saves to S3.
Run as a Railway cron service on a weekly schedule.

Usage:
    PYTHONPATH=src uv run python -m regwatch.weekly_digest
    PYTHONPATH=src uv run python -m regwatch.weekly_digest --dry-run
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import date, timedelta

import httpx
from dotenv import load_dotenv

from regwatch.summary import (
    generate_weekly_summary,
    save_weekly_summary,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Slack webhook for admin notifications
SLACK_ADMIN_WEBHOOK_URL = os.getenv("SLACK_ADMIN_WEBHOOK_URL")


async def send_admin_notification(
    summary_result: dict,
    success: bool,
    error_msg: str | None = None,
) -> bool:
    """Send admin notification about weekly digest generation."""
    webhook_url = SLACK_ADMIN_WEBHOOK_URL

    if not webhook_url:
        logger.info("SLACK_ADMIN_WEBHOOK_URL not configured, skipping admin notification")
        return False

    if success:
        status_emoji = ":white_check_mark:"
        status_text = "Weekly Digest Generated Successfully"
        color = "#22c55e"
    else:
        status_emoji = ":x:"
        status_text = "Weekly Digest Generation Failed"
        color = "#ef4444"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{status_emoji} {status_text}",
                "emoji": True,
            },
        },
    ]

    if success:
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Period:*\n{summary_result['period_start']} to {summary_result['period_end']}"},
                {"type": "mrkdwn", "text": f"*Documents:*\n{summary_result['total_documents']} total, {summary_result['material_documents']} material"},
            ],
        })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Error:*\n```{error_msg}```",
            },
        })

    message = {"blocks": blocks}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=message, timeout=10.0)
            response.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")
        return False


async def run_weekly_digest(dry_run: bool = False) -> dict:
    """
    Run the weekly digest generation.

    Args:
        dry_run: If True, generate but don't save to S3

    Returns:
        Summary result dict
    """
    logger.info("Starting weekly digest generation...")

    # Calculate period (last 7 days)
    end_date = date.today()
    start_date = end_date - timedelta(days=7)

    logger.info(f"Generating summary for {start_date} to {end_date}")

    try:
        # Generate summary
        summary = generate_weekly_summary(start_date, end_date)

        result = {
            "period_start": summary.period_start,
            "period_end": summary.period_end,
            "total_documents": summary.total_documents,
            "material_documents": summary.material_documents,
            "documents_by_topic": summary.documents_by_topic,
        }

        logger.info(f"Summary generated: {result['total_documents']} documents, {result['material_documents']} material")

        if dry_run:
            logger.info("[DRY RUN] Would save summary to S3")
            print("\nExecutive Summary:")
            print("-" * 50)
            print(summary.executive_summary)
            print("-" * 50)
        else:
            # Save to S3
            save_weekly_summary(summary)
            logger.info("Summary saved to S3")

            # Send admin notification
            await send_admin_notification(result, success=True)

        return result

    except Exception as e:
        logger.error(f"Weekly digest generation failed: {e}")

        # Send failure notification
        if not dry_run:
            await send_admin_notification({}, success=False, error_msg=str(e))

        raise


def main():
    """CLI entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Generate weekly regulatory digest"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate summary but don't save to S3",
    )

    args = parser.parse_args()

    try:
        result = asyncio.run(run_weekly_digest(dry_run=args.dry_run))

        print("\nWeekly Digest Result:")
        print(f"  Period: {result['period_start']} to {result['period_end']}")
        print(f"  Total documents: {result['total_documents']}")
        print(f"  Material documents: {result['material_documents']}")
        print(f"  Topics: {result['documents_by_topic']}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
