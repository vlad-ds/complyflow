"""
Weekly regulatory summary generation.

Reads materiality analysis from the registry and generates a digest,
storing it in S3 for frontend access.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from langfuse import observe
from openai import OpenAI
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

from regwatch.materiality_registry import MaterialityRecord, MaterialityRegistry
from regwatch.storage import get_storage

logger = logging.getLogger(__name__)

# Prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Summary storage location
SUMMARY_SUBFOLDER = None  # Root of regwatch cache
SUMMARY_FILENAME = "weekly_summary"

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


@dataclass
class DocumentSummary:
    """Summary of a single regulatory document."""

    celex: str
    topic: str
    title: str
    analyzed_at: str
    eurlex_url: str
    is_material: bool
    relevance: str
    summary: str
    impact: str | None
    action_required: str | None


@dataclass
class WeeklySummary:
    """Weekly regulatory digest."""

    period_start: str  # ISO date
    period_end: str  # ISO date
    generated_at: str  # ISO datetime
    total_documents: int
    material_documents: int
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
            "material_documents": self.material_documents,
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


def load_materiality_registry() -> MaterialityRegistry:
    """Load the materiality registry from storage."""
    registry = MaterialityRegistry()
    registry.load()
    return registry


@observe(name="regwatch-weekly-summary")
def generate_weekly_summary(
    start_date: date | None = None,
    end_date: date | None = None,
) -> WeeklySummary:
    """
    Generate a weekly summary from the materiality registry.

    Args:
        start_date: Start of period (default: 7 days ago)
        end_date: End of period (default: today)

    Returns:
        WeeklySummary with digest
    """
    # Default to last 7 days
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=7)

    logger.info(f"Generating weekly summary for {start_date} to {end_date}")

    # Load registry
    registry = load_materiality_registry()

    # Get records for period
    records = registry.get_records_for_period(
        start_date.isoformat(),
        end_date.isoformat(),
    )
    logger.info(f"Found {len(records)} documents in period")

    if not records:
        return WeeklySummary(
            period_start=start_date.isoformat(),
            period_end=end_date.isoformat(),
            generated_at=datetime.utcnow().isoformat(),
            total_documents=0,
            material_documents=0,
            documents_by_topic={},
            executive_summary="No new regulatory documents were published during this period.",
            documents=[],
        )

    # Count by topic
    docs_by_topic: dict[str, int] = {}
    material_count = 0
    for record in records:
        topic = record.topic
        docs_by_topic[topic] = docs_by_topic.get(topic, 0) + 1
        if record.is_material:
            material_count += 1

    # Convert records to document summaries
    doc_summaries = [
        DocumentSummary(
            celex=r.celex,
            topic=r.topic,
            title=r.title,
            analyzed_at=r.analyzed_at,
            eurlex_url=r.eurlex_url,
            is_material=r.is_material,
            relevance=r.relevance,
            summary=r.summary,
            impact=r.impact,
            action_required=r.action_required,
        )
        for r in records
    ]

    # Generate executive summary using LLM
    executive_summary = _generate_executive_summary(records, start_date, end_date)

    return WeeklySummary(
        period_start=start_date.isoformat(),
        period_end=end_date.isoformat(),
        generated_at=datetime.utcnow().isoformat(),
        total_documents=len(records),
        material_documents=material_count,
        documents_by_topic=docs_by_topic,
        executive_summary=executive_summary,
        documents=doc_summaries,
    )


def _generate_executive_summary(
    records: list[MaterialityRecord],
    start_date: date,
    end_date: date,
) -> str:
    """Generate an executive summary of all documents using GPT-5 Mini."""
    if not records:
        return "No regulatory updates during this period."

    # Filter to material documents for the summary
    material_records = [r for r in records if r.is_material]

    if not material_records:
        return f"During this period, {len(records)} regulatory documents were processed. None were identified as having material impact on the organization's operations."

    # Format document summaries for the prompt
    doc_list = []
    for r in material_records:
        impact_str = f" Impact: {r.impact}" if r.impact else ""
        doc_list.append(
            f"- **{r.topic}** ({r.celex}): {r.summary}{impact_str}"
        )
    doc_text = "\n".join(doc_list)

    prompt = f"""You are preparing an executive summary of regulatory updates for a Berlin-based technology-focused asset manager with ~€1.7B AUM.

**Period:** {start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}
**Total Documents:** {len(records)}
**Material Documents:** {len(material_records)}

**Material Documents:**
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


def save_weekly_summary(summary: WeeklySummary) -> str:
    """
    Save weekly summary to S3 for frontend access.

    Args:
        summary: The weekly summary to save

    Returns:
        The storage key where summary was saved
    """
    storage = get_storage()

    # Save as JSON
    content = json.dumps(summary.to_dict(), indent=2)
    storage.write(SUMMARY_FILENAME, content, subfolder=SUMMARY_SUBFOLDER)

    logger.info(f"Saved weekly summary to {SUMMARY_FILENAME}")
    return SUMMARY_FILENAME


def load_weekly_summary() -> WeeklySummary | None:
    """
    Load the latest weekly summary from S3.

    Returns:
        WeeklySummary if found, None otherwise
    """
    storage = get_storage()
    content = storage.read(SUMMARY_FILENAME, subfolder=SUMMARY_SUBFOLDER)

    if not content:
        logger.info("No weekly summary found in storage")
        return None

    try:
        data = json.loads(content)
        return WeeklySummary(
            period_start=data["period_start"],
            period_end=data["period_end"],
            generated_at=data["generated_at"],
            total_documents=data["total_documents"],
            material_documents=data["material_documents"],
            documents_by_topic=data["documents_by_topic"],
            executive_summary=data["executive_summary"],
            documents=[DocumentSummary(**d) for d in data["documents"]],
        )
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"Failed to parse weekly summary: {e}")
        return None


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

    # Build document sections (only material documents)
    doc_sections = []
    for doc in summary.documents:
        if not doc.is_material:
            continue

        relevance_color = {
            "high": "#dc2626",
            "medium": "#f59e0b",
            "low": "#16a34a",
        }.get(doc.relevance, "#6b7280")

        impact_html = ""
        if doc.impact:
            impact_html = f"<p><strong>Impact:</strong> {doc.impact}</p>"

        action_html = ""
        if doc.action_required:
            action_html = f"<p><strong>Action Required:</strong> {doc.action_required}</p>"

        doc_sections.append(f"""
        <div class="document">
            <div class="doc-header">
                <span class="topic">{doc.topic}</span>
                <span class="relevance" style="background-color: {relevance_color}">{doc.relevance.upper()}</span>
            </div>
            <h3>{doc.title}</h3>
            <p class="celex">CELEX: <a href="{doc.eurlex_url}">{doc.celex}</a></p>
            <p>{doc.summary}</p>
            {impact_html}
            {action_html}
        </div>
        """)

    docs_html = "\n".join(doc_sections) if doc_sections else "<p>No material documents in this period.</p>"

    # Topic breakdown
    topic_items = [
        f"<li>{get_topic_name(topic)}: {count} document(s)</li>"
        for topic, count in sorted(summary.documents_by_topic.items())
    ]
    topics_html = "<ul>" + "".join(topic_items) + "</ul>" if topic_items else "<p>No documents.</p>"

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
            <span class="meta-item"><strong>{summary.material_documents}</strong> material</span>
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
        <h2>Material Documents</h2>
        {docs_html}
    </div>

    <div class="footer">
        Generated by ComplyFlow
    </div>
</body>
</html>
"""
    return html
