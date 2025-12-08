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
    pdf_url: str | None = Field(default=None, description="URL to PDF file in storage")


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


class FieldUpdateRequest(BaseModel):
    """Request body for PATCH /contracts/{id}/fields."""

    field_name: str = Field(
        description="Name of the field to update (e.g., 'parties', 'expiration_date')"
    )
    original_value: Any = Field(
        description="The original AI-extracted value (for correction tracking)"
    )
    new_value: Any = Field(description="The new corrected value")


class FieldUpdateResponse(BaseModel):
    """Response from PATCH /contracts/{id}/fields."""

    success: bool = True
    field_name: str
    new_value: Any
    correction_logged: bool = Field(
        description="Whether a correction was logged (true if value changed)"
    )


class ContractDeleteResponse(BaseModel):
    """Response from DELETE /contracts/{id}."""

    success: bool = True
    id: str = Field(description="Deleted contract record ID")


# --- Citation Models ---


class Citation(BaseModel):
    """A citation record with quote, reasoning, and AI's original value for a field."""

    id: str = Field(description="Citation record ID")
    field_name: str = Field(description="Name of the extracted field")
    quote: str = Field(default="", description="Exact verbatim text from document")
    reasoning: str = Field(default="", description="AI's interpretation logic")
    ai_value: str = Field(default="", description="AI's original extracted value (JSON string)")


class CitationsResponse(BaseModel):
    """Response from GET /contracts/{id}/citations."""

    contract_id: str
    citations: list[Citation]


# --- Chat Models ---


class ChatMessage(BaseModel):
    """A message in the conversation history."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Request body for POST /regwatch/chat."""

    query: str = Field(description="The user's question")
    history: list[ChatMessage] = Field(
        default=[],
        description="Conversation history for context",
    )


class ChatSource(BaseModel):
    """A source chunk used to generate the answer."""

    doc_id: str = Field(description="Document CELEX ID")
    title: str | None = Field(default=None, description="Document title")
    text: str = Field(description="Chunk text")
    topic: str | None = Field(default=None, description="Regulatory topic (DORA, MiCA, etc.)")
    score: float = Field(description="Similarity score (0-1)")


class ChatResponse(BaseModel):
    """Response from POST /regwatch/chat."""

    answer: str = Field(description="Generated answer")
    sources: list[ChatSource] = Field(description="Source chunks used for the answer")
    rewritten_query: str | None = Field(
        default=None,
        description="Query after rewriting (if history was provided)",
    )
    usage: dict | None = Field(default=None, description="Token usage statistics")


# --- Weekly Summary Models ---


class DocumentSummaryResponse(BaseModel):
    """Summary of a single regulatory document."""

    celex: str = Field(description="CELEX document identifier")
    topic: str = Field(description="Regulatory topic (DORA, MiCA, etc.)")
    title: str = Field(description="Document title")
    analyzed_at: str = Field(description="When the document was analyzed")
    eurlex_url: str = Field(description="Link to EUR-Lex document")
    is_material: bool = Field(description="Whether the document is material to BIT Capital")
    relevance: str = Field(description="Relevance level (high, medium, low, none)")
    summary: str = Field(description="Brief summary of the document")
    impact: str | None = Field(default=None, description="Impact on BIT Capital")
    action_required: str | None = Field(default=None, description="Action required")


class WeeklySummaryResponse(BaseModel):
    """Weekly regulatory digest response."""

    period_start: str = Field(description="Start date of the period (ISO format)")
    period_end: str = Field(description="End date of the period (ISO format)")
    generated_at: str = Field(description="When the summary was generated")
    total_documents: int = Field(description="Total number of documents in the period")
    material_documents: int = Field(description="Number of material documents")
    documents_by_topic: dict[str, int] = Field(description="Document count by topic")
    executive_summary: str = Field(description="Executive summary of the period")
    documents: list[DocumentSummaryResponse] = Field(description="Individual document summaries")


# --- Contracts Chat Models ---


class ContractsChatRequest(BaseModel):
    """Request body for POST /contracts/chat."""

    query: str = Field(description="The user's question about contracts")
    history: list[ChatMessage] = Field(
        default=[],
        description="Conversation history for context",
    )


class ContractsChatSource(BaseModel):
    """A source from contract content search."""

    contract_id: str = Field(description="Airtable record ID")
    filename: str = Field(description="Contract filename")
    text: str = Field(description="Relevant text excerpt")
    score: float = Field(description="Similarity score (0-1)")


class ContractsChatResponse(BaseModel):
    """Response from POST /contracts/chat."""

    answer: str = Field(description="Generated answer")
    sources: list[ContractsChatSource] = Field(
        default=[],
        description="Contract sources used for the answer (from semantic search)",
    )
    usage: dict | None = Field(default=None, description="Token usage statistics")
