"""
Simple PDF export for weekly regulatory summaries using reportlab.

No system dependencies required - pure Python.
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _sanitize_text(text: str) -> str:
    """Replace problematic Unicode characters with ASCII equivalents."""
    if not text:
        return text
    # Replace en-dash, em-dash, and other problematic chars
    replacements = {
        "\u2011": "-",  # non-breaking hyphen
        "\u2013": "-",  # en-dash
        "\u2014": "-",  # em-dash
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
        "\u2026": "...",  # ellipsis
        "\u00a0": " ",  # non-breaking space
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


def generate_summary_pdf(summary) -> bytes:
    """
    Generate a PDF from a WeeklySummary dataclass.

    Args:
        summary: WeeklySummary object

    Returns:
        PDF as bytes
    """
    buffer = BytesIO()
    pdf_doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=12,
        textColor=colors.HexColor("#1e40af"),
    )
    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor("#374151"),
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        spaceAfter=8,
        leading=14,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#6b7280"),
    )
    doc_title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica-Bold",
        spaceAfter=4,
    )

    # Build content
    story = []

    # Title
    story.append(Paragraph("Weekly Regulatory Summary", title_style))
    story.append(Paragraph(f"{summary.period_start} to {summary.period_end}", meta_style))
    story.append(Spacer(1, 6 * mm))

    # Stats table
    stats_data = [
        ["Total Documents", "Material", "Regulatory Areas"],
        [str(summary.total_documents), str(summary.material_documents), str(len(summary.documents_by_topic))],
    ]
    stats_table = Table(stats_data, colWidths=[55 * mm, 55 * mm, 55 * mm])
    stats_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 8 * mm))

    # Executive summary
    story.append(Paragraph("Executive Summary", heading_style))
    # Clean up the executive summary text for PDF
    exec_text = _sanitize_text(summary.executive_summary).replace("\n\n", "<br/><br/>").replace("\n", " ")
    story.append(Paragraph(exec_text, body_style))

    # Topic breakdown
    if summary.documents_by_topic:
        story.append(Paragraph("Documents by Topic", heading_style))
        for topic, count in sorted(summary.documents_by_topic.items()):
            story.append(Paragraph(f"• {topic}: {count} document(s)", body_style))

    # Material documents
    material_docs = [d for d in summary.documents if d.is_material]
    if material_docs:
        story.append(Paragraph("Material Documents", heading_style))

        for reg_doc in material_docs:
            # Document header
            relevance_label = f"[{reg_doc.relevance.upper()}]"
            story.append(Paragraph(f"<b>{reg_doc.topic}</b> {relevance_label}", doc_title_style))
            story.append(Paragraph(_sanitize_text(reg_doc.title), body_style))
            story.append(Paragraph(f"CELEX: {reg_doc.celex}", meta_style))
            story.append(Paragraph(_sanitize_text(reg_doc.summary), body_style))

            if reg_doc.impact:
                story.append(Paragraph(f"<b>Impact:</b> {_sanitize_text(reg_doc.impact)}", body_style))
            if reg_doc.action_required:
                story.append(Paragraph(f"<b>Action Required:</b> {_sanitize_text(reg_doc.action_required)}", body_style))

            story.append(Spacer(1, 4 * mm))

    # Footer
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("Generated by ComplyFlow", meta_style))

    # Build PDF
    pdf_doc.build(story)
    return buffer.getvalue()
