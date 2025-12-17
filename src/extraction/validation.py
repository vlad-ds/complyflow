"""Citation validation for extracted contract fields.

Verifies that raw_snippet values from LLM extraction actually exist
in the source document text.
"""

import re
from dataclasses import dataclass


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace for fuzzy matching.

    Collapses all whitespace (spaces, newlines, tabs) into single spaces
    and strips leading/trailing whitespace.
    """
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class CitationValidation:
    """Result of validating a citation against source text."""

    field_name: str
    snippet: str
    found: bool
    confidence: float  # 1.0 if exact match, 0.0 if not found


def validate_citation(
    field_name: str,
    snippet: str,
    source_text: str,
) -> CitationValidation:
    """Validate that a snippet exists in the source text.

    Args:
        field_name: Name of the field being validated
        snippet: The raw_snippet from LLM extraction
        source_text: The full extracted PDF text

    Returns:
        CitationValidation with match results
    """
    # Empty snippets are valid (field not found in document)
    if not snippet or not snippet.strip():
        return CitationValidation(
            field_name=field_name,
            snippet=snippet,
            found=True,  # Empty is valid
            confidence=1.0,
        )

    # Normalize both for comparison
    normalized_snippet = normalize_whitespace(snippet)
    normalized_source = normalize_whitespace(source_text)

    # Check for substring match
    found = normalized_snippet in normalized_source

    return CitationValidation(
        field_name=field_name,
        snippet=snippet,
        found=found,
        confidence=1.0 if found else 0.0,
    )


def validate_extraction_citations(
    extraction: dict,
    source_text: str,
) -> dict:
    """Validate all citations in an extraction result.

    Args:
        extraction: The extraction dict with field objects containing raw_snippet
        source_text: The full extracted PDF text

    Returns:
        Dict with validation results per field and summary stats
    """
    fields_to_validate = [
        "parties",
        "contract_type",
        "agreement_date",
        "effective_date",
        "expiration_date",
        "governing_law",
        "notice_period",
        "renewal_term",
    ]

    validations = []

    for field_name in fields_to_validate:
        field_data = extraction.get(field_name, {})
        snippet = field_data.get("raw_snippet", "")

        validation = validate_citation(field_name, snippet, source_text)
        validations.append(validation)

    # Calculate summary stats
    non_empty = [v for v in validations if v.snippet and v.snippet.strip()]
    valid_count = sum(1 for v in non_empty if v.found)
    total_count = len(non_empty)

    return {
        "validations": [
            {
                "field": v.field_name,
                "found": v.found,
                "confidence": v.confidence,
                "snippet_preview": v.snippet[:100] + "..." if len(v.snippet) > 100 else v.snippet,
            }
            for v in validations
        ],
        "summary": {
            "total_citations": total_count,
            "valid_citations": valid_count,
            "citation_accuracy": valid_count / total_count if total_count > 0 else 1.0,
        },
        "all_valid": all(v.found for v in validations),
    }
