"""
Deadline alert service for contract deadline monitoring.

Checks Airtable for contracts with deadlines approaching in 1 week or 1 month
and sends Slack notifications.

Usage:
    PYTHONPATH=src uv run python -m alerts.deadlines
    PYTHONPATH=src uv run python -m alerts.deadlines --dry-run
    PYTHONPATH=src uv run python -m alerts.deadlines --date 2024-12-15
"""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime

import httpx
from dotenv import load_dotenv
from pyairtable import Api


# Deadline fields to monitor
DEADLINE_FIELDS = {
    "expiration_date": "Expiration Date",
    "notice_deadline": "Notice Deadline",
    "first_renewal_date": "First Renewal Date",
}


@dataclass
class UpcomingDeadline:
    """Represents an upcoming deadline for a contract."""

    record_id: str
    filename: str
    parties: str
    contract_type: str
    field_name: str  # e.g., "expiration_date"
    field_label: str  # e.g., "Expiration Date"
    deadline_date: date
    days_away: int  # 7 or 30
    airtable_url: str


def get_airtable_contracts() -> list[dict]:
    """Fetch reviewed contracts from Airtable."""
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")

    if not api_key or not base_id:
        raise ValueError("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must be set")

    api = Api(api_key)
    table = api.table(base_id, "Contracts")
    # Only check reviewed contracts - skip those still under review
    return table.all(formula="{status} = 'reviewed'", max_records=1000)


def get_airtable_url(record_id: str) -> str:
    """Get the direct URL to a record in Airtable."""
    base_id = os.environ.get("AIRTABLE_BASE_ID")
    # Table ID would require an API call, so use a simplified URL
    return f"https://airtable.com/{base_id}/Contracts/{record_id}"


def parse_date(date_str: str | None) -> date | None:
    """Parse ISO date string to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def get_deadline_window(deadline: date, today: date) -> int | None:
    """
    Check if a deadline falls in an alert window.

    Returns:
        7 if deadline is exactly 7 days away
        30 if deadline is exactly 30 days away
        None otherwise
    """
    days_diff = (deadline - today).days

    if days_diff == 7:
        return 7
    if days_diff == 30:
        return 30
    return None


def format_parties(parties_json: str | None) -> str:
    """Format parties JSON string for display."""
    if not parties_json:
        return "Unknown"

    try:
        parties = json.loads(parties_json)
        if isinstance(parties, list):
            if len(parties) == 0:
                return "Unknown"
            if len(parties) == 1:
                return parties[0]
            if len(parties) == 2:
                return f"{parties[0]} & {parties[1]}"
            return f"{parties[0]} & {len(parties) - 1} others"
        return str(parties)
    except (json.JSONDecodeError, TypeError):
        return str(parties_json)


def check_upcoming_deadlines(today: date | None = None) -> list[UpcomingDeadline]:
    """
    Check all contracts for upcoming deadlines.

    Args:
        today: Override today's date (for testing)

    Returns:
        List of UpcomingDeadline objects for contracts with deadlines
        exactly 7 or 30 days away
    """
    if today is None:
        today = date.today()

    contracts = get_airtable_contracts()
    upcoming = []

    for record in contracts:
        fields = record.get("fields", {})
        record_id = record["id"]

        # Extract display info
        filename = fields.get("filename", "Unknown")
        parties = format_parties(fields.get("parties"))
        contract_type = fields.get("contract_type", "Unknown")
        if contract_type:
            contract_type = contract_type.title()

        # Check each deadline field
        for field_name, field_label in DEADLINE_FIELDS.items():
            date_str = fields.get(field_name)
            deadline = parse_date(date_str)

            if deadline is None:
                continue

            days_away = get_deadline_window(deadline, today)
            if days_away is not None:
                upcoming.append(
                    UpcomingDeadline(
                        record_id=record_id,
                        filename=filename,
                        parties=parties,
                        contract_type=contract_type,
                        field_name=field_name,
                        field_label=field_label,
                        deadline_date=deadline,
                        days_away=days_away,
                        airtable_url=get_airtable_url(record_id),
                    )
                )

    return upcoming


async def send_slack_alert(deadline: UpcomingDeadline) -> bool:
    """
    Send Slack notification for an upcoming deadline.

    Returns:
        True if notification sent successfully, False otherwise
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

    if not webhook_url:
        print("SLACK_WEBHOOK_URL not configured, skipping notification")
        return False

    # Format the deadline date
    date_str = deadline.deadline_date.strftime("%B %d, %Y")

    # Determine urgency emoji and text
    if deadline.days_away == 7:
        emoji = ":rotating_light:"
        urgency = "1 Week Away"
    else:
        emoji = ":warning:"
        urgency = "1 Month Away"

    # Compliance officer mention
    compliance_officer = os.environ.get("SLACK_COMPLIANCE_OFFICER_ID", "")
    mention = f"<@{compliance_officer}> " if compliance_officer else ""

    message = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} Contract Deadline Alert: {urgency}",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{mention}A contract deadline is approaching.",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Parties:*\n{deadline.parties}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{deadline.contract_type}"},
                    {"type": "mrkdwn", "text": f"*{deadline.field_label}:*\n{date_str}"},
                    {"type": "mrkdwn", "text": f"*Days Remaining:*\n{deadline.days_away}"},
                ],
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"*File:* `{deadline.filename}`"}],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Review in Airtable"},
                        "url": deadline.airtable_url,
                        "style": "primary",
                    }
                ],
            },
        ],
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=message, timeout=10.0)
            response.raise_for_status()
            return True
    except Exception as e:
        print(f"Failed to send Slack notification: {e}")
        return False


async def send_admin_summary(
    check_date: date,
    upcoming: list[UpcomingDeadline],
    notifications_sent: int,
    notifications_failed: int,
) -> bool:
    """
    Send a summary message to the Admin Slack channel.

    This runs every time the service executes, for monitoring purposes.
    """
    webhook_url = os.environ.get("SLACK_ADMIN_WEBHOOK_URL")

    if not webhook_url:
        print("SLACK_ADMIN_WEBHOOK_URL not configured, skipping admin summary")
        return False

    date_str = check_date.strftime("%B %d, %Y")

    # Build the deadline list
    if upcoming:
        deadline_lines = []
        for d in upcoming:
            deadline_lines.append(
                f"• *{d.parties}* - {d.field_label} on {d.deadline_date} ({d.days_away} days)"
            )
        deadlines_text = "\n".join(deadline_lines)
    else:
        deadlines_text = "_No deadlines within alert windows (7 or 30 days)_"

    # Status emoji
    if notifications_failed > 0:
        status_emoji = ":warning:"
        status_text = f"Sent {notifications_sent}, Failed {notifications_failed}"
    elif notifications_sent > 0:
        status_emoji = ":white_check_mark:"
        status_text = f"Sent {notifications_sent} alert(s) to compliance channel"
    else:
        status_emoji = ":white_check_mark:"
        status_text = "No alerts needed"

    message = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} Deadline Check Complete",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Date:*\n{date_str}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{status_text}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Upcoming Deadlines ({len(upcoming)}):*\n{deadlines_text}",
                },
            },
        ],
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=message, timeout=10.0)
            response.raise_for_status()
            return True
    except Exception as e:
        print(f"Failed to send admin summary: {e}")
        return False


async def run_deadline_check(today: date | None = None, dry_run: bool = False) -> dict:
    """
    Run the full deadline check and optionally send notifications.

    Args:
        today: Override today's date (for testing)
        dry_run: If True, just list deadlines without sending notifications

    Returns:
        Summary dict with counts of deadlines found and notifications sent
    """
    check_date = today or date.today()
    print(f"Checking deadlines for {check_date}...")

    upcoming = check_upcoming_deadlines(check_date)
    print(f"Found {len(upcoming)} upcoming deadlines")

    sent = 0
    failed = 0

    for deadline in upcoming:
        print(
            f"  - {deadline.parties}: {deadline.field_label} "
            f"on {deadline.deadline_date} ({deadline.days_away} days)"
        )

        if not dry_run:
            success = await send_slack_alert(deadline)
            if success:
                sent += 1
            else:
                failed += 1

    # Send admin summary (always, even on dry run)
    if not dry_run:
        await send_admin_summary(check_date, upcoming, sent, failed)

    return {
        "date": str(check_date),
        "deadlines_found": len(upcoming),
        "notifications_sent": sent,
        "notifications_failed": failed,
    }


def main():
    """CLI entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Check for upcoming contract deadlines and send Slack alerts"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Check deadlines relative to this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List deadlines without sending notifications",
    )

    args = parser.parse_args()

    # Parse date if provided
    check_date = None
    if args.date:
        try:
            check_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            print(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            sys.exit(1)

    # Run the check
    result = asyncio.run(run_deadline_check(check_date, dry_run=args.dry_run))

    print("\nSummary:")
    print(f"  Date: {result['date']}")
    print(f"  Deadlines found: {result['deadlines_found']}")
    if not args.dry_run:
        print(f"  Notifications sent: {result['notifications_sent']}")
        print(f"  Notifications failed: {result['notifications_failed']}")

        if result["notifications_failed"] > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
