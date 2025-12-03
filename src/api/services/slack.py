"""
Slack notification service for contract alerts.
"""

import os
from typing import Any

import httpx


def format_date(d: dict | str | None) -> str:
    """Format a date dict or string for display."""
    if d is None:
        return "N/A"
    if isinstance(d, str):
        if d == "perpetual":
            return "Perpetual"
        if d == "conditional":
            return "Conditional"
        return d
    if isinstance(d, dict) and "year" in d:
        return f"{d['month']}/{d['day']}/{d['year']}"
    return "N/A"


def format_parties(parties: Any) -> str:
    """Format parties for display."""
    if parties is None:
        return "Unknown"
    if isinstance(parties, list):
        if len(parties) == 0:
            return "Unknown"
        if len(parties) == 1:
            return parties[0]
        if len(parties) == 2:
            return f"{parties[0]} & {parties[1]}"
        return f"{parties[0]} & {len(parties) - 1} others"
    if isinstance(parties, dict):
        return format_parties(parties.get("normalized_value"))
    return str(parties)


async def notify_new_contract(
    contract: dict,
    airtable_record_id: str,
    airtable_url: str,
) -> bool:
    """
    Send Slack notification for a new contract upload.

    Args:
        contract: Contract data with extraction and computed_dates
        airtable_record_id: The Airtable record ID
        airtable_url: Direct link to the Airtable record

    Returns:
        True if notification sent successfully, False otherwise
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

    if not webhook_url:
        # Slack not configured - skip silently
        print("SLACK_WEBHOOK_URL not configured, skipping notification")
        return False

    extraction = contract.get("extraction", {})
    computed_dates = contract.get("computed_dates", {})

    # Extract display values
    parties = extraction.get("parties")
    parties_str = format_parties(parties)

    contract_type = extraction.get("contract_type")
    if isinstance(contract_type, dict):
        contract_type = contract_type.get("normalized_value", "Unknown")
    contract_type = contract_type or "Unknown"

    exp_date = computed_dates.get("expiration_date")
    exp_str = format_date(exp_date)

    notice_deadline = computed_dates.get("notice_deadline")
    notice_str = format_date(notice_deadline)

    filename = contract.get("filename", "Unknown")

    message = {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "New Contract Uploaded",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Parties:*\n{parties_str}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{contract_type.title()}"},
                    {"type": "mrkdwn", "text": f"*Expires:*\n{exp_str}"},
                    {"type": "mrkdwn", "text": f"*Notice Deadline:*\n{notice_str}"},
                ],
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"*File:* `{filename}`"}],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Review in Airtable"},
                        "url": airtable_url,
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
