"""
ComplyFlow Contract Intake API.

FastAPI server for contract upload, metadata extraction, and Airtable storage.
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from dotenv import load_dotenv

# Load environment variables before other imports
load_dotenv()

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from api.models import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatSource,
    Citation,
    CitationsResponse,
    ContractDeleteResponse,
    ContractListResponse,
    ContractRecord,
    ContractReviewRequest,
    ContractReviewResponse,
    ContractUploadResponse,
    DocumentSummaryResponse,
    ErrorResponse,
    FieldUpdateRequest,
    FieldUpdateResponse,
    HealthResponse,
    WeeklySummaryResponse,
)
from api.logging import get_logger, log_error
from api.services.airtable import AirtableService
from api.services.extraction import process_contract
from api.services.slack import notify_new_contract
from api.utils.retry import LLMRetryExhaustedError, LLMTimeoutError
from contracts.embedding import embed_and_store_contract, delete_contract_embeddings

# Constants
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# API Key from environment
API_KEY = os.getenv("API_KEY")

logger = get_logger(__name__)


async def verify_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Verify the API key from the X-API-Key header.

    If API_KEY env var is not set, authentication is disabled (dev mode).
    """
    if not API_KEY:
        # No API key configured - auth disabled
        return

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Provide X-API-Key header.",
        )

    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key.",
        )


# Global service instances
_airtable: AirtableService | None = None


def get_airtable() -> AirtableService:
    """Get or create Airtable service instance."""
    global _airtable
    if _airtable is None:
        _airtable = AirtableService()
    return _airtable


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize services on startup."""
    logger.info("Starting ComplyFlow API...")

    # Initialize Airtable service
    global _airtable
    try:
        _airtable = AirtableService()
        logger.info("Airtable service initialized")
    except Exception as e:
        logger.warning(f"Could not initialize Airtable: {type(e).__name__}: {e}")

    logger.info("ComplyFlow API ready")
    yield

    # Cleanup on shutdown
    logger.info("Shutting down ComplyFlow API...")
    _airtable = None


app = FastAPI(
    title="ComplyFlow Contract Intake",
    description="API for uploading contracts, extracting metadata, and storing in Airtable",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Health check endpoint."""
    return HealthResponse()


@app.post(
    "/contracts/upload",
    response_model=ContractUploadResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid input (bad file, empty, too large)"},
        401: {"model": ErrorResponse, "description": "Unauthorized - invalid or missing API key"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
        502: {"model": ErrorResponse, "description": "LLM service error after retries"},
        504: {"model": ErrorResponse, "description": "LLM timeout"},
    },
    tags=["Contracts"],
    dependencies=[Depends(verify_api_key)],
)
async def upload_contract(
    file: Annotated[UploadFile, File(description="PDF contract file to upload")],
    pdf_url: Annotated[str | None, Form(description="URL where PDF is stored (e.g., Supabase Storage)")] = None,
):
    """
    Upload a contract PDF for processing.

    This endpoint:
    1. Extracts text from the PDF
    2. Uses LLM to extract metadata (parties, dates, terms, etc.)
    3. Computes derived dates (notice deadline, renewal date)
    4. Stores the contract in Airtable with status "under_review"
    5. Sends a Slack notification (if configured)

    Optionally accepts pdf_url to store a link to the PDF in Airtable.
    """
    # Validate filename
    if not file.filename:
        logger.warning("Upload rejected: no filename provided")
        raise HTTPException(status_code=400, detail="No filename provided")

    filename = file.filename
    logger.info(f"Upload started: {filename}")

    # Validate file extension
    if not filename.lower().endswith(".pdf"):
        logger.warning(f"Upload rejected: invalid extension for {filename}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: expected .pdf, got .{filename.split('.')[-1] if '.' in filename else 'none'}",
        )

    # Read file content
    try:
        pdf_bytes = await file.read()
    except Exception as e:
        log_error(logger, "File read failed", e, filename=filename)
        raise HTTPException(
            status_code=400,
            detail=f"Could not read uploaded file: {type(e).__name__}",
        )

    # Validate file size
    file_size_mb = len(pdf_bytes) / (1024 * 1024)
    if len(pdf_bytes) == 0:
        logger.warning(f"Upload rejected: empty file {filename}")
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    if len(pdf_bytes) > MAX_FILE_SIZE_BYTES:
        logger.warning(
            f"Upload rejected: file too large {filename} ({file_size_mb:.1f}MB > {MAX_FILE_SIZE_MB}MB)"
        )
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {file_size_mb:.1f}MB exceeds {MAX_FILE_SIZE_MB}MB limit",
        )

    logger.info(f"File validated: {filename} ({file_size_mb:.2f}MB)")

    # Process contract (extraction + date computation)
    try:
        contract_data = process_contract(pdf_bytes, filename)
    except ValueError as e:
        # ValueError = expected errors like scanned PDFs
        logger.warning(f"Extraction rejected for {filename}: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except LLMTimeoutError as e:
        log_error(logger, "LLM timeout", e, filename=filename)
        raise HTTPException(
            status_code=504,
            detail=f"LLM extraction timed out after {e.timeout_seconds}s. Please try again.",
        )
    except LLMRetryExhaustedError as e:
        log_error(logger, "LLM retry exhausted", e, filename=filename)
        raise HTTPException(
            status_code=502,
            detail=f"LLM extraction failed after {e.attempts} attempts: {type(e.last_error).__name__}",
        )
    except Exception as e:
        log_error(logger, "Extraction failed", e, filename=filename)
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {type(e).__name__}: {e}",
        )

    logger.info(f"Extraction complete for {filename}")

    # Add pdf_url if provided
    if pdf_url:
        contract_data["pdf_url"] = pdf_url

    # Store in Airtable
    try:
        airtable = get_airtable()
        record = airtable.create_contract(contract_data)
        record_id = record["id"]
        airtable_url = airtable.get_airtable_url(record_id)
        logger.info(f"Stored in Airtable: {filename} -> {record_id}")
    except Exception as e:
        log_error(logger, "Airtable storage failed", e, filename=filename)
        raise HTTPException(
            status_code=500,
            detail=f"Database storage failed: {type(e).__name__}: {e}",
        )

    # Embed contract and store in Qdrant (blocking - upload fails if this fails)
    try:
        embedding_result = embed_and_store_contract(
            text=contract_data["text"],
            contract_id=record_id,
            filename=filename,
            extraction=contract_data["extraction"],
        )
        logger.info(
            f"Embedded {filename}: {embedding_result['chunks_count']} chunks, "
            f"{embedding_result['points_upserted']} points"
        )
    except Exception as e:
        # Embedding failed - delete the Airtable record to maintain consistency
        log_error(logger, "Embedding failed, rolling back Airtable record", e, filename=filename)
        try:
            airtable.delete_contract(record_id)
            logger.info(f"Rolled back Airtable record {record_id}")
        except Exception as rollback_err:
            log_error(logger, "Rollback failed", rollback_err, record_id=record_id)
        raise HTTPException(
            status_code=500,
            detail=f"Contract embedding failed: {type(e).__name__}: {e}",
        )

    # Send Slack notification (fire and forget, don't fail if Slack fails)
    try:
        await notify_new_contract(contract_data, record_id)
        logger.info(f"Slack notification sent for {filename}")
    except Exception as e:
        log_error(logger, "Slack notification failed (non-fatal)", e, filename=filename)

    logger.info(f"Upload complete: {filename} -> {record_id}")

    return ContractUploadResponse(
        contract_id=record_id,
        filename=filename,
        extraction=contract_data["extraction"],
        computed_dates=contract_data["computed_dates"],
        status="under_review",
        airtable_url=airtable_url,
        created_at=datetime.utcnow(),
        usage=contract_data.get("usage"),
        pdf_url=pdf_url,
    )


@app.get(
    "/contracts/{record_id}",
    response_model=ContractRecord,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse},
    },
    tags=["Contracts"],
    dependencies=[Depends(verify_api_key)],
)
async def get_contract(record_id: str):
    """Get a contract by its Airtable record ID."""
    airtable = get_airtable()
    record = airtable.get_contract(record_id)

    if not record:
        raise HTTPException(status_code=404, detail="Contract not found")

    return ContractRecord(
        id=record["id"],
        fields=record["fields"],
        created_time=record.get("createdTime"),
    )


@app.get(
    "/contracts/{record_id}/citations",
    response_model=CitationsResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Contract not found"},
    },
    tags=["Contracts"],
    dependencies=[Depends(verify_api_key)],
)
async def get_contract_citations(record_id: str):
    """
    Get all citations (quotes and reasoning) for a contract.

    Returns the exact PDF quotes and AI reasoning for each extracted field.
    """
    airtable = get_airtable()

    # Verify contract exists
    record = airtable.get_contract(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Contract not found")

    citations_data = airtable.get_citations(record_id)

    return CitationsResponse(
        contract_id=record_id,
        citations=[Citation(**c) for c in citations_data],
    )


@app.delete(
    "/contracts/{record_id}",
    response_model=ContractDeleteResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Contract not found"},
    },
    tags=["Contracts"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_contract(record_id: str):
    """Delete a contract by its Airtable record ID."""
    airtable = get_airtable()

    # Verify contract exists
    existing = airtable.get_contract(record_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")

    try:
        airtable.delete_contract(record_id)
        logger.info(f"Deleted contract from Airtable: {record_id}")
    except Exception as e:
        log_error(logger, "Delete failed", e, record_id=record_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete contract: {type(e).__name__}: {e}",
        )

    # Delete embeddings from Qdrant (non-fatal if this fails)
    try:
        deleted_points = delete_contract_embeddings(record_id)
        logger.info(f"Deleted {deleted_points} embeddings for contract: {record_id}")
    except Exception as e:
        log_error(logger, "Embedding deletion failed (non-fatal)", e, record_id=record_id)

    return ContractDeleteResponse(id=record_id)


@app.patch(
    "/contracts/{record_id}/review",
    response_model=ContractReviewResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse},
    },
    tags=["Contracts"],
    dependencies=[Depends(verify_api_key)],
)
async def review_contract(record_id: str, body: ContractReviewRequest):
    """Mark a contract as reviewed."""
    airtable = get_airtable()

    # Verify contract exists
    existing = airtable.get_contract(record_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Update status
    if body.reviewed:
        updated = airtable.mark_reviewed(record_id)
    else:
        updated = airtable.update_contract(record_id, {"status": "under_review"})

    return ContractReviewResponse(
        id=updated["id"],
        status=updated["fields"].get("status", "unknown"),
        reviewed_at=updated["fields"].get("reviewed_at"),
    )


# Allowed fields for update
UPDATABLE_FIELDS = {
    "parties",
    "contract_type",
    "agreement_date",
    "effective_date",
    "expiration_date",
    "notice_deadline",
    "first_renewal_date",
    "governing_law",
    "notice_period",
    "renewal_term",
}


@app.patch(
    "/contracts/{record_id}/fields",
    response_model=FieldUpdateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid field name"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "Contract not found"},
    },
    tags=["Contracts"],
    dependencies=[Depends(verify_api_key)],
)
async def update_contract_field(record_id: str, body: FieldUpdateRequest):
    """
    Update a single field and log the correction for ML training.

    This endpoint:
    1. Updates the specified field in Airtable
    2. Logs the correction to a separate Corrections table if the value changed
    3. Returns success status and whether a correction was logged

    Corrections are used to build a training dataset for improving AI extraction.
    """
    # Validate field name
    if body.field_name not in UPDATABLE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid field name: '{body.field_name}'. "
            f"Allowed fields: {', '.join(sorted(UPDATABLE_FIELDS))}",
        )

    airtable = get_airtable()

    # Verify contract exists
    existing = airtable.get_contract(record_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Contract not found")

    # Update field and log correction
    try:
        updated, correction = airtable.update_field_with_correction(
            record_id=record_id,
            field_name=body.field_name,
            original_value=body.original_value,
            new_value=body.new_value,
        )
        logger.info(
            f"Updated field '{body.field_name}' for contract {record_id}, "
            f"correction_logged={correction is not None}"
        )
    except Exception as e:
        log_error(logger, "Field update failed", e, record_id=record_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update field: {type(e).__name__}: {e}",
        )

    return FieldUpdateResponse(
        success=True,
        field_name=body.field_name,
        new_value=body.new_value,
        correction_logged=correction is not None,
    )


@app.get(
    "/contracts",
    response_model=ContractListResponse,
    responses={401: {"model": ErrorResponse, "description": "Unauthorized"}},
    tags=["Contracts"],
    dependencies=[Depends(verify_api_key)],
)
async def list_contracts(
    status: Annotated[
        str | None,
        Query(description="Filter by status: 'under_review' or 'reviewed'"),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Maximum number of records to return"),
    ] = 50,
):
    """List contracts with optional status filter."""
    airtable = get_airtable()

    # Validate status if provided
    if status and status not in ("under_review", "reviewed"):
        raise HTTPException(
            status_code=400,
            detail="status must be 'under_review' or 'reviewed'",
        )

    records = airtable.list_contracts(status=status, limit=limit)

    contracts = [
        ContractRecord(
            id=r["id"],
            fields=r["fields"],
            created_time=r.get("createdTime"),
        )
        for r in records
    ]

    return ContractListResponse(contracts=contracts, total=len(contracts))


# --- Regwatch Chat Endpoint ---


@app.post(
    "/regwatch/chat",
    response_model=ChatResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    tags=["Regwatch"],
    dependencies=[Depends(verify_api_key)],
)
async def regwatch_chat(body: ChatRequest):
    """
    RAG chat endpoint for regulatory questions.

    This endpoint:
    1. Rewrites follow-up questions to be standalone (if history provided)
    2. Embeds the query using Snowflake Arctic
    3. Retrieves top-K relevant chunks from Qdrant
    4. Generates an answer using GPT-5-mini with citations

    The frontend should send conversation history with each request.
    """
    from chatbot.rag import ChatMessage as RagChatMessage
    from chatbot.rag import chat

    logger.info(f"Chat request: {body.query[:50]}... (history: {len(body.history)} messages)")

    # Convert API models to internal models
    history = [
        RagChatMessage(role=msg.role, content=msg.content)
        for msg in body.history
    ]

    try:
        result = chat(query=body.query, history=history, top_k=20)
    except Exception as e:
        log_error(logger, "Chat failed", e, query=body.query[:50])
        raise HTTPException(
            status_code=500,
            detail=f"Chat failed: {type(e).__name__}: {e}",
        )

    # Convert internal models to API response
    sources = [
        ChatSource(
            doc_id=src.doc_id,
            title=src.title,
            text=src.text,
            topic=src.topic,
            score=src.score,
        )
        for src in result.sources
    ]

    logger.info(f"Chat response: {len(sources)} sources, {len(result.answer)} chars")

    return ChatResponse(
        answer=result.answer,
        sources=sources,
        rewritten_query=result.rewritten_query,
        usage=result.usage,
    )


# --- Weekly Summary Endpoints ---


@app.get(
    "/regwatch/summary/weekly",
    response_model=WeeklySummaryResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "No summary available"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    tags=["Regwatch"],
    dependencies=[Depends(verify_api_key)],
)
async def get_weekly_summary(
    regenerate: Annotated[
        bool,
        Query(description="Force regeneration instead of reading from cache"),
    ] = False,
):
    """
    Get weekly regulatory summary.

    Returns the pre-generated weekly digest from storage.
    The digest is generated weekly by a cron job.

    Use regenerate=true to force a fresh generation (slower).
    """
    from regwatch.summary import generate_weekly_summary, load_weekly_summary

    # Try to load cached summary first (unless regenerate requested)
    if not regenerate:
        summary = load_weekly_summary()
        if summary:
            logger.info(f"Loaded cached summary: {summary.period_start} to {summary.period_end}")
        else:
            logger.info("No cached summary found, generating fresh")
            summary = None
    else:
        logger.info("Regeneration requested, generating fresh summary")
        summary = None

    # Generate if no cached summary
    if summary is None:
        try:
            summary = generate_weekly_summary()
        except Exception as e:
            log_error(logger, "Weekly summary generation failed", e)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate summary: {type(e).__name__}: {e}",
            )

    # Convert to response model
    documents = [
        DocumentSummaryResponse(
            celex=doc.celex,
            topic=doc.topic,
            title=doc.title,
            analyzed_at=doc.analyzed_at,
            eurlex_url=doc.eurlex_url,
            is_material=doc.is_material,
            relevance=doc.relevance,
            summary=doc.summary,
            impact=doc.impact,
            action_required=doc.action_required,
        )
        for doc in summary.documents
    ]

    return WeeklySummaryResponse(
        period_start=summary.period_start,
        period_end=summary.period_end,
        generated_at=summary.generated_at,
        total_documents=summary.total_documents,
        material_documents=summary.material_documents,
        documents_by_topic=summary.documents_by_topic,
        executive_summary=summary.executive_summary,
        documents=documents,
    )


@app.get(
    "/regwatch/summary/weekly/pdf",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF download of weekly summary",
        },
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        404: {"model": ErrorResponse, "description": "No summary available"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    tags=["Regwatch"],
    dependencies=[Depends(verify_api_key)],
)
async def get_weekly_summary_pdf():
    """
    Download weekly regulatory summary as PDF.

    Returns a PDF of the pre-generated weekly digest from storage.
    """
    from io import BytesIO

    from fastapi.responses import StreamingResponse

    from regwatch.summary import generate_weekly_summary, load_weekly_summary

    logger.info("Generating weekly summary PDF")

    # Try to load cached summary first
    summary = load_weekly_summary()
    if not summary:
        logger.info("No cached summary found, generating fresh")
        try:
            summary = generate_weekly_summary()
        except Exception as e:
            log_error(logger, "Weekly summary generation failed", e)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate summary: {type(e).__name__}: {e}",
            )

    try:
        # Generate PDF using reportlab
        from regwatch.pdf_export import generate_summary_pdf

        pdf_bytes = generate_summary_pdf(summary)

        # Create filename
        filename = f"regulatory_summary_{summary.period_start}_to_{summary.period_end}.pdf"

        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        log_error(logger, "PDF generation failed", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate PDF: {type(e).__name__}: {e}",
        )


# Run with: uvicorn api.main:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
