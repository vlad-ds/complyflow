"""
Materiality analysis for regulatory documents.

Analyzes new regulatory documents using GPT-5 Mini to determine
if they contain material information for the organization, then sends
Slack notifications for material updates.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from langfuse import get_client, observe
from openai import OpenAI
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

from regwatch.config import EURLEX_DOC_URL
from regwatch.materiality_registry import MaterialityRegistry

logger = logging.getLogger(__name__)

# Singleton registry instance
_materiality_registry: MaterialityRegistry | None = None


def get_materiality_registry() -> MaterialityRegistry:
    """Get or create materiality registry instance."""
    global _materiality_registry
    if _materiality_registry is None:
        _materiality_registry = MaterialityRegistry()
        _materiality_registry.load()
    return _materiality_registry


def save_materiality_registry() -> None:
    """Save the materiality registry to storage."""
    if _materiality_registry is not None:
        _materiality_registry.save()

# Prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Configuration
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://spec-whisperer-38.lovable.app")
SLACK_REGWATCH_WEBHOOK_URL = os.getenv("SLACK_REGWATCH_WEBHOOK_URL")

# Initialize OpenAI instrumentation for Langfuse tracing
_instrumentor = OpenAIInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument()

# Singleton OpenAI client
_openai_client: OpenAI | None = None


def _get_openai() -> OpenAI:
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client


def _load_prompt(name: str) -> str:
    """Load a prompt from the prompts directory."""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text()


@dataclass
class MaterialityResult:
    """Result of materiality analysis."""

    celex: str
    topic: str
    title: str
    is_material: bool
    relevance: str  # high, medium, low, none
    summary: str
    impact: str | None
    action_required: str | None
    eurlex_url: str
    slack_notified: bool = False


@observe(name="regwatch-materiality-analysis")
def analyze_materiality(
    celex: str,
    topic: str,
    title: str,
    content: str,
    max_content_chars: int = 15000,
) -> MaterialityResult:
    """
    Analyze a regulatory document for materiality to the organization.

    Args:
        celex: CELEX number of the document
        topic: Regulatory topic (DORA, MiCA, etc.)
        title: Document title
        content: Full text content of the document
        max_content_chars: Maximum content length to send to LLM

    Returns:
        MaterialityResult with analysis
    """
    logger.info(f"Analyzing materiality for {celex} ({topic})")

    # Update Langfuse trace with tags
    langfuse = get_client()
    langfuse.update_current_trace(
        tags=["regwatch-materiality", "source:regwatch-ingest"],
        metadata={"celex": celex, "topic": topic},
    )

    # Truncate content if too long
    content_excerpt = content[:max_content_chars]
    if len(content) > max_content_chars:
        content_excerpt += "\n\n[... content truncated ...]"

    # Load and format prompt
    prompt_template = _load_prompt("materiality_analysis_v1")
    prompt = prompt_template.format(
        celex=celex,
        topic=topic,
        title=title,
        content=content_excerpt,
    )

    # Call GPT-5 Mini
    client = _get_openai()
    response = client.chat.completions.create(
        model="gpt-5-mini-2025-08-07",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=4096,
    )

    response_text = response.choices[0].message.content.strip()

    # Parse JSON from response
    try:
        # Extract JSON from markdown code block if present
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        else:
            json_str = response_text

        result_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse materiality response for {celex}: {e}")
        # Default to non-material if parsing fails
        result_data = {
            "is_material": False,
            "relevance": "none",
            "summary": "Analysis failed - could not parse LLM response",
            "impact": None,
            "action_required": None,
        }

    eurlex_url = EURLEX_DOC_URL.format(celex=celex)

    return MaterialityResult(
        celex=celex,
        topic=topic,
        title=title,
        is_material=result_data.get("is_material", False),
        relevance=result_data.get("relevance", "none"),
        summary=result_data.get("summary", ""),
        impact=result_data.get("impact"),
        action_required=result_data.get("action_required"),
        eurlex_url=eurlex_url,
    )


async def send_materiality_alert(result: MaterialityResult) -> bool:
    """
    Send Slack notification for a material regulatory update.

    Args:
        result: MaterialityResult from analysis

    Returns:
        True if notification sent successfully, False otherwise
    """
    webhook_url = SLACK_REGWATCH_WEBHOOK_URL

    if not webhook_url:
        logger.warning("SLACK_REGWATCH_WEBHOOK_URL not configured, skipping notification")
        return False

    if not result.is_material:
        logger.debug(f"Skipping Slack notification for non-material document: {result.celex}")
        return False

    # Relevance emoji
    relevance_emoji = {
        "high": ":rotating_light:",
        "medium": ":warning:",
        "low": ":information_source:",
    }.get(result.relevance, ":page_facing_up:")

    # Build message blocks
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{relevance_emoji} New Regulatory Update: {result.topic}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{result.title}*\n\n{result.summary}",
            },
        },
    ]

    # Add impact if present
    if result.impact:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Impact:*\n{result.impact}",
            },
        })

    # Add action required if present
    if result.action_required:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Action Required:*\n{result.action_required}",
            },
        })

    # Add context with CELEX
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"*CELEX:* `{result.celex}` | *Relevance:* {result.relevance.title()}"}
        ],
    })

    # Add action buttons
    chat_url = f"{FRONTEND_URL}/compychat"
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "View Document"},
                "url": result.eurlex_url,
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Ask Compliance Bot"},
                "url": chat_url,
                "style": "primary",
            },
        ],
    })

    message = {"blocks": blocks}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(webhook_url, json=message, timeout=10.0)
            response.raise_for_status()
            logger.info(f"Sent Slack notification for {result.celex}")
            return True
    except Exception as e:
        logger.error(f"Failed to send Slack notification for {result.celex}: {e}")
        return False


async def analyze_and_notify(
    celex: str,
    topic: str,
    title: str,
    content: str,
) -> MaterialityResult:
    """
    Analyze a document for materiality, save to registry, and send Slack notification if material.

    This is the main entry point called from the ingestion pipeline.

    Args:
        celex: CELEX number
        topic: Regulatory topic
        title: Document title
        content: Full document text

    Returns:
        MaterialityResult with analysis
    """
    registry = get_materiality_registry()

    # Check if already analyzed (avoid duplicate notifications)
    if registry.has_analysis(celex):
        logger.info(f"Document {celex} already analyzed, skipping")
        existing = registry.get_record(celex)
        if existing:
            return MaterialityResult(
                celex=existing.celex,
                topic=existing.topic,
                title=existing.title,
                is_material=existing.is_material,
                relevance=existing.relevance,
                summary=existing.summary,
                impact=existing.impact,
                action_required=existing.action_required,
                eurlex_url=existing.eurlex_url,
                slack_notified=existing.slack_notified,
            )

    # Run materiality analysis
    result = analyze_materiality(celex, topic, title, content)

    # Save to registry
    slack_notified = False
    if result.is_material:
        # Send Slack notification
        slack_notified = await send_materiality_alert(result)

    registry.add_result(
        celex=result.celex,
        topic=result.topic,
        title=result.title,
        is_material=result.is_material,
        relevance=result.relevance,
        summary=result.summary,
        impact=result.impact,
        action_required=result.action_required,
        eurlex_url=result.eurlex_url,
        slack_notified=slack_notified,
    )

    # Save registry after each analysis
    registry.save()

    # Update result with notification status
    result.slack_notified = slack_notified

    return result
