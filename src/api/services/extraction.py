"""
Contract extraction service that wraps the existing extraction pipeline.

Processes PDFs in-memory without saving to disk.
"""

import io
import json
import tempfile
from pathlib import Path
from typing import Any

import pdfplumber

from extraction.extract import extract_contract_metadata, _get_json_schema, _get_contract_types_str
from extraction.schema import ExtractionResponse
from llm.openai_provider import OpenAIProvider, DateComputationResponse
from prompts import load_prompt


def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes (in-memory processing).

    Args:
        pdf_bytes: Raw PDF file bytes

    Returns:
        Concatenated text from all pages
    """
    text_parts = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def extract_metadata_from_text(text: str, model: str = "gpt-5-mini") -> dict:
    """
    Run LLM extraction on contract text.

    Args:
        text: Contract text content
        model: OpenAI model to use

    Returns:
        Dict with extraction results
    """
    provider = OpenAIProvider(model=model)

    # Load prompt
    prompt_template = load_prompt("extraction_v1")
    prompt = prompt_template.format(contract_types=_get_contract_types_str())

    # Get JSON schema
    json_schema = _get_json_schema()

    # Call LLM
    llm_response = provider.extract_json(
        prompt=prompt,
        document=text,
        json_schema=json_schema,
        model=model,
    )

    # Parse response
    result = ExtractionResponse.model_validate_json(llm_response.content)

    # Convert to dict for JSON serialization
    extraction_dict = result.model_dump()

    return {
        "extraction": extraction_dict,
        "usage": {
            "model": llm_response.model,
            "input_tokens": llm_response.input_tokens,
            "output_tokens": llm_response.output_tokens,
        },
    }


def prepare_date_fields(extraction: dict) -> dict:
    """
    Prepare date fields from extraction for date computation.

    Args:
        extraction: Extraction dict (the "extraction" key from extract_metadata_from_text)

    Returns:
        Dict with date fields formatted for compute_dates
    """
    # Get raw values
    agreement_date_val = extraction.get("agreement_date", {}).get("normalized_value", "")
    effective_date_val = extraction.get("effective_date", {}).get("normalized_value", "")

    # Infer effective_date from agreement_date if missing
    effective_date_inferred = effective_date_val if effective_date_val else agreement_date_val
    effective_date_was_inferred = not effective_date_val and bool(agreement_date_val)

    return {
        "agreement_date": {
            "raw_snippet": extraction.get("agreement_date", {}).get("raw_snippet", ""),
            "normalized_value": agreement_date_val,
        },
        "effective_date": {
            "raw_snippet": extraction.get("effective_date", {}).get("raw_snippet", ""),
            "normalized_value": effective_date_val,
        },
        "effective_date_inferred": {
            "normalized_value": effective_date_inferred,
            "was_inferred": effective_date_was_inferred,
        },
        "expiration_date": {
            "raw_snippet": extraction.get("expiration_date", {}).get("raw_snippet", ""),
            "normalized_value": extraction.get("expiration_date", {}).get("normalized_value", ""),
        },
        "notice_period": {
            "raw_snippet": extraction.get("notice_period", {}).get("raw_snippet", ""),
            "normalized_value": extraction.get("notice_period", {}).get("normalized_value", ""),
        },
        "renewal_term": {
            "raw_snippet": extraction.get("renewal_term", {}).get("raw_snippet", ""),
            "normalized_value": extraction.get("renewal_term", {}).get("normalized_value", ""),
        },
    }


def compute_dates_from_extraction(extraction: dict, model: str = "gpt-5-mini") -> dict:
    """
    Compute dates from extraction results.

    Args:
        extraction: Extraction dict (the "extraction" key)
        model: OpenAI model to use

    Returns:
        Dict with computed dates
    """
    provider = OpenAIProvider(model=model)

    # Load prompt
    prompt = load_prompt("date_computation_v1")

    # Prepare date fields
    date_fields = prepare_date_fields(extraction)

    # Compute dates
    response: DateComputationResponse = provider.compute_dates(
        prompt=prompt,
        contract_data=date_fields,
        model=model,
    )

    return {
        "computed_dates": response.content,
        "usage": {
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "latency_seconds": response.latency_seconds,
        },
    }


def process_contract(pdf_bytes: bytes, filename: str, model: str = "gpt-5-mini") -> dict:
    """
    Full contract processing pipeline: PDF -> extraction -> date computation.

    Args:
        pdf_bytes: Raw PDF file bytes
        filename: Original filename for reference
        model: OpenAI model to use

    Returns:
        Dict with filename, extraction, computed_dates, and usage stats
    """
    # Step 1: Extract text from PDF
    text = extract_text_from_bytes(pdf_bytes)

    if not text.strip():
        raise ValueError("Could not extract text from PDF - file may be scanned/image-based")

    # Step 2: Run LLM extraction
    extraction_result = extract_metadata_from_text(text, model=model)

    # Step 3: Compute dates
    date_result = compute_dates_from_extraction(
        extraction_result["extraction"],
        model=model,
    )

    # Combine results
    return {
        "filename": filename,
        "extraction": extraction_result["extraction"],
        "computed_dates": date_result["computed_dates"],
        "usage": {
            "extraction": extraction_result["usage"],
            "date_computation": date_result["usage"],
        },
    }
