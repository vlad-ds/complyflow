"""
Contract extraction service that wraps the existing extraction pipeline.

Processes PDFs in-memory without saving to disk.
All LLM calls are tagged with "source:api" for Langfuse tracking.
"""

import io
import json
from typing import Any

import pdfplumber
from openai import APIError, APITimeoutError, RateLimitError

from api.logging import get_logger
from api.utils.retry import llm_retry
from extraction.extract import _get_json_schema, _get_contract_types_str
from extraction.schema import ExtractionResponse
from extraction.validation import validate_extraction_citations
from llm.openai_provider import OpenAIProvider, DateComputationResponse
from llm.base import LLMResponse
from prompts import load_prompt

logger = get_logger(__name__)

# Tag for all API-originated LLM calls
API_TAGS = ["source:api"]

# Maximum contract text length (500KB) - beyond our longest CUAD contract
# Prevents accidentally processing massive files or corrupted PDFs
MAX_CONTRACT_TEXT_LENGTH = 500_000

# Exceptions that should trigger a retry
RETRYABLE_EXCEPTIONS = (APIError, APITimeoutError, RateLimitError)


@llm_retry(
    timeout_seconds=120.0,
    max_retries=3,
    retry_delay_seconds=2.0,
    retryable_exceptions=RETRYABLE_EXCEPTIONS,
)
def _call_extract_json(
    provider: OpenAIProvider,
    prompt: str,
    document: str,
    json_schema: dict,
    model: str,
) -> LLMResponse:
    """Wrapped LLM call for extraction with retry logic."""
    return provider.extract_json(
        prompt=prompt,
        document=document,
        json_schema=json_schema,
        model=model,
        tags=API_TAGS,
    )


@llm_retry(
    timeout_seconds=120.0,
    max_retries=3,
    retry_delay_seconds=2.0,
    retryable_exceptions=RETRYABLE_EXCEPTIONS,
)
def _call_compute_dates(
    provider: OpenAIProvider,
    prompt: str,
    contract_data: dict,
    model: str,
) -> DateComputationResponse:
    """Wrapped LLM call for date computation with retry logic."""
    return provider.compute_dates(
        prompt=prompt,
        contract_data=contract_data,
        model=model,
        tags=API_TAGS,
    )


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
    Run LLM extraction on contract text with timeout and retry.

    Args:
        text: Contract text content
        model: OpenAI model to use

    Returns:
        Dict with extraction results

    Raises:
        LLMTimeoutError: If extraction times out after all retries
        LLMRetryExhaustedError: If extraction fails after all retries
    """
    provider = OpenAIProvider(model=model)

    # Load prompt
    prompt_template = load_prompt("extraction_v1")
    prompt = prompt_template.format(contract_types=_get_contract_types_str())

    # Get JSON schema
    json_schema = _get_json_schema()

    logger.info(f"Starting metadata extraction with model={model}")

    # Call with retry decorator
    llm_response = _call_extract_json(
        provider=provider,
        prompt=prompt,
        document=text,
        json_schema=json_schema,
        model=model,
    )

    # Parse response
    result = ExtractionResponse.model_validate_json(llm_response.content)
    extraction_dict = result.model_dump()

    logger.info(
        f"Extraction complete: {llm_response.input_tokens} input tokens, "
        f"{llm_response.output_tokens} output tokens"
    )

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
    Compute dates from extraction results with timeout and retry.

    Args:
        extraction: Extraction dict (the "extraction" key)
        model: OpenAI model to use

    Returns:
        Dict with computed dates

    Raises:
        LLMTimeoutError: If date computation times out after all retries
        LLMRetryExhaustedError: If date computation fails after all retries
    """
    provider = OpenAIProvider(model=model)

    # Load prompt
    prompt = load_prompt("date_computation_v1")

    # Prepare date fields
    date_fields = prepare_date_fields(extraction)

    logger.info(f"Starting date computation with model={model}")

    # Call with retry decorator
    response = _call_compute_dates(
        provider=provider,
        prompt=prompt,
        contract_data=date_fields,
        model=model,
    )

    logger.info(
        f"Date computation complete: {response.input_tokens} input tokens, "
        f"{response.output_tokens} output tokens, {response.latency_seconds:.2f}s"
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

    # Length guard - reject files beyond our expected maximum
    if len(text) > MAX_CONTRACT_TEXT_LENGTH:
        raise ValueError(
            f"Contract text too long ({len(text):,} chars). "
            f"Maximum supported is {MAX_CONTRACT_TEXT_LENGTH:,} chars."
        )

    # Step 2: Run LLM extraction
    extraction_result = extract_metadata_from_text(text, model=model)

    # Step 3: Validate citations against source text
    citation_validation = validate_extraction_citations(
        extraction_result["extraction"],
        text,
    )
    logger.info(
        f"Citation validation: {citation_validation['summary']['valid_citations']}/"
        f"{citation_validation['summary']['total_citations']} citations verified"
    )

    # Step 4: Compute dates
    date_result = compute_dates_from_extraction(
        extraction_result["extraction"],
        model=model,
    )

    # Combine results
    return {
        "filename": filename,
        "extraction": extraction_result["extraction"],
        "computed_dates": date_result["computed_dates"],
        "citation_validation": citation_validation,
        "text": text,  # Include extracted text for embedding
        "usage": {
            "extraction": extraction_result["usage"],
            "date_computation": date_result["usage"],
        },
    }
