"""
Weekly regulatory summary generation.

Generates a digest of regulatory updates from the past week,
suitable for viewing on the compliance website or exporting as PDF.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from langfuse import observe
from openai import OpenAI
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

from regwatch.config import EURLEX_DOC_URL, EURLEX_FEEDS
from regwatch.registry import DocumentRegistry
from regwatch.storage import get_storage

logger = logging.getLogger(__name__)

# Prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Initialize OpenAI instrumentation
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
class DocumentSummary:
    """Summary of a single regulatory document."""

    celex: str
    topic: str
    title: str
    indexed_at: str
    eurlex_url: str
    summary: str
    relevance: str  # high, medium, low
    key_points: list[str]


@dataclass
class WeeklySummary:
    """Weekly regulatory digest."""

    period_start: str  # ISO date
    period_end: str  # ISO date
    generated_at: str  # ISO datetime
    total_documents: int
    documents_by_topic: dict[str, int]
    executive_summary: str
    documents: list[DocumentSummary]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "generated_at": self.generated_at,
            "total_documents": self.total_documents,
            "documents_by_topic": self.documents_by_topic,
            "executive_summary": self.executive_summary,
            "documents": [asdict(d) for d in self.documents],
        }


def get_topic_name(topic_code: str) -> str:
    """Get human-readable topic name from code."""
    topic_names = {
        "DORA": "Digital Operational Resilience Act",
        "MiCA": "Markets in Crypto-Assets",
        "AIFMD": "Alternative Investment Fund Managers Directive",
        "MiFID": "Markets in Financial Instruments Directive II",
        "AML": "Anti-Money Laundering",
        "AI": "EU AI Act",
        "ESG": "Sustainable Finance Disclosure Regulation",
    }
    return topic_names.get(topic_code, topic_code)


def get_documents_for_period(
    start_date: date,
    end_date: date,
    registry_filename: str = "indexed_documents.json",
) -> list[dict]:
    """
    Get all documents indexed within a date range.

    Args:
        start_date: Start of period (inclusive)
        end_date: End of period (inclusive)
        registry_filename: Registry file to use

    Returns:
        List of document dicts with celex, topic, indexed_at, chunk_count
    """
    registry = DocumentRegistry(registry_filename)
    registry.load()

    documents = []
    for doc in registry.get_all_indexed():
        # Parse indexed_at timestamp
        try:
            indexed_dt = datetime.fromisoformat(doc.indexed_at)
            indexed_date = indexed_dt.date()
        except (ValueError, TypeError):
            continue

        # Check if within range
        if start_date <= indexed_date <= end_date:
            documents.append({
                "celex": doc.celex,
                "topic": doc.topic,
                "indexed_at": doc.indexed_at,
                "chunk_count": doc.chunk_count,
            })

    return documents


def get_document_content(celex: str, topic: str) -> str | None:
    """
    Read document content from cache.

    Args:
        celex: CELEX number
        topic: Topic (used as cache subfolder)

    Returns:
        Document content or None if not found
    """
    storage = get_storage()
    return storage.read(celex, subfolder=topic)


@observe(name="regwatch-weekly-summary")
def generate_weekly_summary(
    start_date: date | None = None,
    end_date: date | None = None,
    max_content_chars: int = 8000,
) -> WeeklySummary:
    """
    Generate a weekly summary of regulatory updates.

    Args:
        start_date: Start of period (default: 7 days ago)
        end_date: End of period (default: today)
        max_content_chars: Max content per document for summarization

    Returns:
        WeeklySummary with digest
    """
    # Default to last 7 days
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    logger.info(f"Generating weekly summary for {start_date} to {end_date}")

    # Get documents for period
    documents = get_documents_for_period(start_date, end_date)
    logger.info(f"Found {len(documents)} documents in period")

    if not documents:
        return WeeklySummary(
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            generated_at=datetime.utcnow().isoformat(),
            total_documents=0,
            documents_by_topic={},
            executive_summary="No new regulatory documents were published during this period.",
            documents=[],
        )

    # Count by topic
    docs_by_topic: dict[str, int] = {}
    for doc in documents:
        topic = doc["topic"]
        docs_by_topic[topic] = docs_by_topic.get(topic, 0) + 1

    # Fetch content and generate individual summaries
    doc_summaries: list[DocumentSummary] = []

    for doc in documents:
        content = get_document_content(doc["celex"], doc["topic"])
        if not content:
            logger.warning(f"No content found for {doc['celex']}")
            continue

        # Truncate content for summarization
        content_excerpt = content[:max_content_chars]

        # Generate summary for this document
        summary_data = _summarize_document(
            celex=doc["celex"],
            topic=doc["topic"],
            content=content_excerpt,
        )

        doc_summaries.append(DocumentSummary(
            celex=doc["celex"],
            topic=doc["topic"],
            title=summary_data.get("title", doc["celex"]),
            indexed_at=doc["indexed_at"],
            eurlex_url=EURLEX_DOC_URL.format(celex=doc["celex"]),
            summary=summary_data.get("summary", ""),
            relevance=summary_data.get("relevance", "medium"),
            key_points=summary_data.get("key_points", []),
        ))

    # Generate executive summary
    executive_summary = _generate_executive_summary(doc_summaries, start_date, end_date)

    return WeeklySummary(
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        generated_at=datetime.utcnow().isoformat(),
        total_documents=len(doc_summaries),
        documents_by_topic=docs_by_topic,
        executive_summary=executive_summary,
        documents=doc_summaries,
    )


def _summarize_document(celex: str, topic: str, content: str) -> dict:
    """Summarize a single document using GPT-5 Mini."""
    prompt = f"""Analyze this EU regulatory document and provide a brief summary.

**CELEX:** {celex}
**Topic:** {topic}

**Content (excerpt):**
{content}

Respond in JSON format:
```json
{{
  "title": "Short descriptive title for the document",
  "summary": "2-3 sentence summary of what this document does",
  "relevance": "high/medium/low (for a tech-focused asset manager)",
  "key_points": ["Key point 1", "Key point 2", "Key point 3"]
}}
```
"""

    client = _get_openai()
    response = client.chat.completions.create(
        model="gpt-5-mini-2025-08-07",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=2048,
    )

    response_text = response.choices[0].message.content.strip()

    try:
        # Extract JSON from response
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

        return json.loads(json_str)
    except json.JSONDecodeError:
        return {
            "title": celex,
            "summary": "Summary generation failed",
            "relevance": "medium",
            "key_points": [],
        }


def _generate_executive_summary(
    documents: list[DocumentSummary],
    start_date: date,
    end_date: date,
) -> str:
    """Generate an executive summary of all documents."""
    if not documents:
        return "No regulatory updates during this period."

    # Format document summaries for the prompt
    doc_list = []
    for doc in documents:
        doc_list.append(
            f"- **{doc.topic}** ({doc.celex}): {doc.summary}"
        )
    doc_text = "\n".join(doc_list)

    prompt = f"""You are preparing an executive summary of regulatory updates for BIT Capital, a Berlin-based technology-focused asset manager.

**Period:** {start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}
**Total Documents:** {len(documents)}

**Documents:**
{doc_text}

Write a 2-3 paragraph executive summary that:
1. Highlights the most important updates for a tech-focused asset manager with crypto exposure
2. Notes any immediate compliance actions required
3. Uses professional, concise language suitable for senior management

Do not use bullet points. Write in prose.
"""

    client = _get_openai()
    response = client.chat.completions.create(
        model="gpt-5-mini-2025-08-07",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=4096,
    )

    return response.choices[0].message.content.strip()


def generate_summary_html(summary: WeeklySummary) -> str:
    """
    Generate HTML version of the weekly summary for PDF export.

    Args:
        summary: WeeklySummary to render

    Returns:
        HTML string
    """
    # Format dates
    start_dt = datetime.fromisoformat(summary.period_start)
    end_dt = datetime.fromisoformat(summary.period_end)
    period_str = f"{start_dt.strftime('%B %d, %Y')} - {end_dt.strftime('%B %d, %Y')}"

    # Build document sections
    doc_sections = []
    for doc in summary.documents:
        relevance_color = {
            "high": "#dc2626",
            "medium": "#f59e0b",
            "low": "#16a34a",
        }.get(doc.relevance, "#6b7280")

        key_points_html = ""
        if doc.key_points:
            points = "".join(f"<li>{point}</li>" for point in doc.key_points)
            key_points_html = f"<ul>{points}</ul>"

        doc_sections.append(f"""
        <div class="document">
            <div class="doc-header">
                <span class="topic">{doc.topic}</span>
                <span class="relevance" style="background-color: {relevance_color}">{doc.relevance.upper()}</span>
            </div>
            <h3>{doc.title}</h3>
            <p class="celex">CELEX: <a href="{doc.eurlex_url}">{doc.celex}</a></p>
            <p>{doc.summary}</p>
            {key_points_html}
        </div>
        """)

    docs_html = "\n".join(doc_sections)

    # Topic breakdown
    topic_items = [
        f"<li>{get_topic_name(topic)}: {count} document(s)</li>"
        for topic, count in sorted(summary.documents_by_topic.items())
    ]
    topics_html = "<ul>" + "".join(topic_items) + "</ul>"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Weekly Regulatory Summary</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px;
            color: #1f2937;
            line-height: 1.6;
        }}
        .header {{
            border-bottom: 3px solid #2563eb;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        h1 {{
            color: #1e40af;
            margin: 0;
        }}
        .period {{
            color: #6b7280;
            font-size: 1.1em;
            margin-top: 10px;
        }}
        .meta {{
            display: flex;
            gap: 30px;
            margin-top: 15px;
            font-size: 0.9em;
        }}
        .meta-item {{
            background: #f3f4f6;
            padding: 8px 16px;
            border-radius: 4px;
        }}
        .executive-summary {{
            background: #eff6ff;
            border-left: 4px solid #2563eb;
            padding: 20px;
            margin: 30px 0;
        }}
        .executive-summary h2 {{
            margin-top: 0;
            color: #1e40af;
        }}
        .topic-breakdown {{
            margin: 30px 0;
        }}
        .topic-breakdown h2 {{
            color: #374151;
        }}
        .topic-breakdown ul {{
            list-style: none;
            padding: 0;
        }}
        .topic-breakdown li {{
            padding: 8px 0;
            border-bottom: 1px solid #e5e7eb;
        }}
        .documents {{
            margin-top: 40px;
        }}
        .documents h2 {{
            color: #374151;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 10px;
        }}
        .document {{
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        .doc-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .topic {{
            background: #dbeafe;
            color: #1e40af;
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.85em;
        }}
        .relevance {{
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 0.75em;
        }}
        .document h3 {{
            margin: 10px 0;
            color: #111827;
        }}
        .celex {{
            font-size: 0.85em;
            color: #6b7280;
        }}
        .celex a {{
            color: #2563eb;
        }}
        .document ul {{
            background: #f9fafb;
            padding: 15px 15px 15px 35px;
            border-radius: 4px;
        }}
        .document li {{
            margin: 8px 0;
        }}
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
            text-align: center;
            color: #9ca3af;
            font-size: 0.85em;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Weekly Regulatory Summary</h1>
        <div class="period">{period_str}</div>
        <div class="meta">
            <span class="meta-item"><strong>{summary.total_documents}</strong> documents</span>
            <span class="meta-item"><strong>{len(summary.documents_by_topic)}</strong> regulatory areas</span>
        </div>
    </div>

    <div class="executive-summary">
        <h2>Executive Summary</h2>
        <p>{summary.executive_summary.replace(chr(10), '</p><p>')}</p>
    </div>

    <div class="topic-breakdown">
        <h2>Documents by Regulatory Area</h2>
        {topics_html}
    </div>

    <div class="documents">
        <h2>Document Details</h2>
        {docs_html}
    </div>

    <div class="footer">
        Generated by ComplyFlow | BIT Capital Compliance Platform
    </div>
</body>
</html>
"""
    return html
