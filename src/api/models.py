"""
Pydantic models for Contract Intake API request/response schemas.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Date Models ---


class DateField(BaseModel):
    """A specific calendar date."""

    year: int = Field(description="4-digit year")
    month: int = Field(ge=1, le=12, description="Month (1-12)")
    day: int = Field(ge=1, le=31, description="Day of month (1-31)")


# --- Extraction Models ---


class ExtractedField(BaseModel):
    """An extracted field with raw snippet, reasoning, and normalized value."""

    raw_snippet: str = Field(default="", description="Exact verbatim text from document")
    reasoning: str = Field(default="", description="Explanation of interpretation")
    normalized_value: Any = Field(description="Standardized value")


class ExtractionResult(BaseModel):
    """Extraction results from LLM."""

    parties: ExtractedField
    contract_type: ExtractedField
    agreement_date: ExtractedField
    effective_date: ExtractedField
    expiration_date: ExtractedField
    governing_law: ExtractedField
    notice_period: ExtractedField
    renewal_term: ExtractedField


class ComputedDates(BaseModel):
    """Computed date values."""

    agreement_date: DateField | None = None
    effective_date: DateField | None = None
    expiration_date: DateField | str | None = None  # Can be "perpetual" or "conditional"
    notice_deadline: DateField | None = None
    first_renewal_date: DateField | None = None


class UsageStats(BaseModel):
    """Token usage statistics."""

    model: str
    input_tokens: int
    output_tokens: int
    latency_seconds: float | None = None


# --- API Response Models ---


class ContractUploadResponse(BaseModel):
    """Response from POST /contracts/upload."""

    contract_id: str = Field(description="Airtable record ID")
    filename: str = Field(description="Original PDF filename")
    extraction: dict = Field(description="Extracted metadata fields")
    computed_dates: dict = Field(description="Computed date values")
    status: Literal["under_review", "reviewed"] = "under_review"
    airtable_url: str = Field(description="Direct link to Airtable record")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    usage: dict | None = Field(default=None, description="Token usage stats")


class ContractRecord(BaseModel):
    """A contract record from Airtable."""

    id: str = Field(description="Airtable record ID")
    fields: dict = Field(description="Record fields")
    created_time: str | None = None


class ContractListResponse(BaseModel):
    """Response from GET /contracts."""

    contracts: list[ContractRecord]
    total: int


class ContractReviewRequest(BaseModel):
    """Request body for PATCH /contracts/{id}/review."""

    reviewed: bool = True


class ContractReviewResponse(BaseModel):
    """Response from PATCH /contracts/{id}/review."""

    id: str
    status: str
    reviewed_at: str | None = None


class HealthResponse(BaseModel):
    """Response from GET /health."""

    status: str = "ok"
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: str | None = None
