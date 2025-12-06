"""
Metadata extraction utilities for EU regulatory documents.

Extracts structured metadata from CELEX numbers and document headers.
No LLM calls - pure regex parsing.
"""

import re
from dataclasses import dataclass
from datetime import date

# CELEX sector codes
CELEX_SECTORS = {
    "1": "treaties",
    "2": "international_agreements",
    "3": "legislation",
    "4": "internal_agreements",
    "5": "preparatory_acts",
    "6": "case_law",
    "7": "national_transposition",
    "8": "references",
    "9": "other",
    "C": "oj_c_series",  # Official Journal C series
    "E": "efta",
}

# CELEX document type codes (within sector 3 - legislation)
CELEX_DOC_TYPES = {
    "R": "regulation",
    "L": "directive",
    "D": "decision",
    "F": "framework_decision",
    "O": "ecb_orientation",
    "M": "recommendation",
    "S": "decision_ecsc",
    "K": "recommendation_ecsc",
    "A": "opinion",
    "G": "resolution",
    "Q": "institutional_rules",
    "X": "other_acts",
}

# Sector 5 (preparatory) type codes
CELEX_PREP_TYPES = {
    "PC": "proposal_com",
    "DC": "other_com_doc",
    "AP": "ep_position",
    "AG": "council_position",
    "SC": "staff_working_doc",
    "IP": "ep_initiative",
    "BP": "budget_proposal",
    "XC": "other_docs",
}

# Month name to number mapping
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


@dataclass
class DocumentMetadata:
    """Structured metadata extracted from a regulatory document."""

    # From CELEX
    celex: str
    sector: str  # e.g., "legislation", "preparatory_acts"
    year: int
    doc_type: str  # e.g., "regulation", "directive", "proposal_com"
    serial: str
    is_final: bool  # True if legislation, False if proposal

    # From document header
    legal_basis: str | None = None  # "parliament_council", "commission", "commission_delegated"
    adopted_date: date | None = None
    short_subject: str | None = None

    # From RSS/connector
    topic: str | None = None  # e.g., "DORA", "MiCA"
    publication_date: date | None = None
    title: str | None = None
    url: str | None = None

    def to_chunk_metadata(self, chunk_index: int, source_file: str) -> dict:
        """Convert to flat dict for Qdrant payload."""
        return {
            # Document identifiers
            "doc_id": self.celex,
            "source_file": source_file,
            "chunk_index": chunk_index,
            # Document classification
            "topic": self.topic,
            "doc_type": self.doc_type,
            "sector": self.sector,
            "year": self.year,
            "is_final": self.is_final,
            "legal_basis": self.legal_basis,
            # Dates
            "adopted_date": self.adopted_date.isoformat() if self.adopted_date else None,
            "publication_date": self.publication_date.isoformat() if self.publication_date else None,
            # Display
            "title": self.title,
            "short_subject": self.short_subject,
        }


def parse_celex(celex: str) -> dict:
    """
    Parse CELEX number into structured components.

    CELEX structure: [sector][year][type][serial]
    Examples:
        32022R2554 → sector=3, year=2022, type=R, serial=2554
        52025PC0837 → sector=5, year=2025, type=PC, serial=0837
        C_2025_05391 → sector=C, year=2025, type=None, serial=05391

    Returns dict with: sector, sector_name, year, type_code, type_name, serial, is_final
    """
    # Handle C/2025/05391 format (OJ C series)
    if celex.startswith("C"):
        match = re.match(r"C[/_](\d{4})[/_](\d+)", celex)
        if match:
            return {
                "sector": "C",
                "sector_name": CELEX_SECTORS.get("C", "unknown"),
                "year": int(match.group(1)),
                "type_code": None,
                "type_name": "oj_c_document",
                "serial": match.group(2),
                "is_final": True,
            }

    # Standard format: [sector][year][type][serial]
    # Sector 3 (legislation): 32022R2554
    # Sector 5 (preparatory): 52025PC0837
    match = re.match(r"(\d)(\d{4})([A-Z]{1,2})(\d+)", celex)
    if match:
        sector = match.group(1)
        year = int(match.group(2))
        type_code = match.group(3)
        serial = match.group(4)

        # Determine type name based on sector
        if sector == "3":
            type_name = CELEX_DOC_TYPES.get(type_code, "unknown")
        elif sector == "5":
            type_name = CELEX_PREP_TYPES.get(type_code, "unknown")
        else:
            type_name = "unknown"

        return {
            "sector": sector,
            "sector_name": CELEX_SECTORS.get(sector, "unknown"),
            "year": year,
            "type_code": type_code,
            "type_name": type_name,
            "serial": serial,
            "is_final": sector == "3",
        }

    # Fallback: extract year if possible
    year_match = re.search(r"(\d{4})", celex)
    return {
        "sector": "unknown",
        "sector_name": "unknown",
        "year": int(year_match.group(1)) if year_match else None,
        "type_code": None,
        "type_name": "unknown",
        "serial": celex,
        "is_final": False,
    }


def parse_document_header(content: str) -> dict:
    """
    Parse document header to extract legal basis, adopted date, and subject.

    Looks at the first ~1000 characters of the document.

    Returns dict with: legal_basis, adopted_date, short_subject
    """
    header = content[:2000] if content else ""
    header_lower = header.lower()

    # Determine legal basis from first line
    legal_basis = None
    first_line = header.split("\n")[0] if header else ""
    first_line_lower = first_line.lower()

    if "delegated regulation" in first_line_lower or "delegated directive" in first_line_lower:
        legal_basis = "commission_delegated"
    elif "implementing regulation" in first_line_lower or "implementing directive" in first_line_lower:
        legal_basis = "commission_implementing"
    elif "commission regulation" in first_line_lower or "commission directive" in first_line_lower:
        legal_basis = "commission"
    elif "of the european parliament and of the council" in first_line_lower:
        legal_basis = "parliament_council"
    elif "council regulation" in first_line_lower or "council directive" in first_line_lower:
        legal_basis = "council"
    elif "european central bank" in first_line_lower or "ecb" in first_line_lower:
        legal_basis = "ecb"

    # Extract adopted date: "of 14 December 2022"
    adopted_date = None
    date_match = re.search(r"of\s+(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})", header)
    if date_match:
        day = int(date_match.group(1))
        month_str = date_match.group(2).lower()
        year = int(date_match.group(3))
        month = MONTHS.get(month_str)
        if month:
            try:
                adopted_date = date(year, month, day)
            except ValueError:
                pass

    # Extract short subject: text after date line starting with "on" or "laying down"
    short_subject = None
    # Look for pattern: after the date, usually starts with "on " or "laying down"
    subject_match = re.search(
        r"of\s+\d{1,2}\s+[a-zA-Z]+\s+\d{4}\s*\n+(.+?)(?:\n\n|\(Text with)",
        header,
        re.DOTALL | re.IGNORECASE,
    )
    if subject_match:
        subject = subject_match.group(1).strip()
        # Clean up: remove newlines, collapse whitespace
        subject = re.sub(r"\s+", " ", subject)
        # Truncate if too long
        if len(subject) > 200:
            subject = subject[:200] + "..."
        short_subject = subject

    return {
        "legal_basis": legal_basis,
        "adopted_date": adopted_date,
        "short_subject": short_subject,
    }


def extract_metadata(
    celex: str,
    content: str | None = None,
    topic: str | None = None,
    publication_date: date | None = None,
    title: str | None = None,
    url: str | None = None,
) -> DocumentMetadata:
    """
    Extract complete metadata for a document.

    Args:
        celex: CELEX number (e.g., "32022R2554")
        content: Full document text (optional, for header parsing)
        topic: Topic from RSS feed (e.g., "DORA")
        publication_date: Publication date from RSS feed
        title: Title from RSS feed
        url: URL from RSS feed

    Returns:
        DocumentMetadata object with all extracted fields
    """
    # Parse CELEX
    celex_data = parse_celex(celex)

    # Parse header if content provided
    header_data = parse_document_header(content) if content else {}

    return DocumentMetadata(
        celex=celex,
        sector=celex_data["sector_name"],
        year=celex_data["year"] or 0,
        doc_type=celex_data["type_name"],
        serial=celex_data["serial"],
        is_final=celex_data["is_final"],
        legal_basis=header_data.get("legal_basis"),
        adopted_date=header_data.get("adopted_date"),
        short_subject=header_data.get("short_subject"),
        topic=topic,
        publication_date=publication_date,
        title=title,
        url=url,
    )
