"""
Alerts module for contract deadline monitoring.

Standalone service that checks Airtable for upcoming deadlines
and sends Slack notifications.
"""

from alerts.deadlines import check_upcoming_deadlines, run_deadline_check, send_slack_alert

__all__ = ["check_upcoming_deadlines", "run_deadline_check", "send_slack_alert"]
