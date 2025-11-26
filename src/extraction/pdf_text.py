"""PDF text extraction using pdfplumber."""

from pathlib import Path

import pdfplumber


def extract_text_from_pdf(pdf_path: Path | str) -> str:
    """Extract all text from a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Concatenated text from all pages, separated by newlines.
    """
    pdf_path = Path(pdf_path)
    text_parts = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n\n".join(text_parts)


def extract_text_by_page(pdf_path: Path | str) -> list[str]:
    """Extract text from each page of a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of text strings, one per page.
    """
    pdf_path = Path(pdf_path)
    pages = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            pages.append(page_text)

    return pages
