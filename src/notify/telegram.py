"""Telegram notifications for app activity monitoring."""

import asyncio
import logging
import os
from datetime import datetime
from functools import wraps

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

_BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else None


async def _send_async(text: str) -> bool:
    """Send message asynchronously."""
    if not _BASE_URL or not TELEGRAM_CHAT_ID:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{_BASE_URL}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            )
        return True
    except Exception as e:
        logger.debug(f"Notification failed: {e}")
        return False


def _send_sync(text: str) -> bool:
    """Send message synchronously."""
    if not _BASE_URL or not TELEGRAM_CHAT_ID:
        return False
    try:
        with httpx.Client(timeout=5.0) as client:
            client.post(
                f"{_BASE_URL}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            )
        return True
    except Exception as e:
        logger.debug(f"Notification failed: {e}")
        return False


def notify(event: str, details: str = "") -> None:
    """
    Send activity notification (fire-and-forget).

    Does nothing if TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    ts = datetime.utcnow().strftime("%H:%M:%S")
    msg = f"<b>{event}</b>\n{ts} UTC"
    if details:
        msg += f"\n\n{details}"

    # Fire and forget - don't block the request
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_async(msg))
    except RuntimeError:
        # No event loop - use sync
        _send_sync(msg)


def get_chat_id() -> str | None:
    """
    Get chat_id by polling for updates.

    Run this once after messaging the bot to get your chat_id.
    """
    if not _BASE_URL:
        print("TELEGRAM_BOT_TOKEN not set")
        return None

    import httpx
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{_BASE_URL}/getUpdates")
        data = resp.json()

    if data.get("result"):
        for update in data["result"]:
            if "message" in update:
                chat_id = update["message"]["chat"]["id"]
                print(f"Found chat_id: {chat_id}")
                return str(chat_id)

    print("No messages found. Send a message to the bot first.")
    return None


if __name__ == "__main__":
    # Helper to get chat_id
    get_chat_id()
