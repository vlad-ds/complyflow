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

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from api.models import (
    ContractDeleteResponse,
    ContractListResponse,
    ContractRecord,
    ContractReviewRequest,
    ContractReviewResponse,
    ContractUploadResponse,
    ErrorResponse,
    FieldUpdateRequest,
    FieldUpdateResponse,
    HealthResponse,
)
from api.logging import get_logger, log_error
from api.services.airtable import AirtableService
from api.services.extraction import process_contract
from api.services.slack import notify_new_contract
from api.utils.retry import LLMRetryExhaustedError, LLMTimeoutError

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
):
    """
    Upload a contract PDF for processing.

    This endpoint:
    1. Extracts text from the PDF
    2. Uses LLM to extract metadata (parties, dates, terms, etc.)
    3. Computes derived dates (notice deadline, renewal date)
    4. Stores the contract in Airtable with status "under_review"
    5. Sends a Slack notification (if configured)
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

    # Send Slack notification (fire and forget, don't fail if Slack fails)
    try:
        await notify_new_contract(contract_data, record_id, airtable_url)
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
        logger.info(f"Deleted contract: {record_id}")
    except Exception as e:
        log_error(logger, "Delete failed", e, record_id=record_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete contract: {type(e).__name__}: {e}",
        )

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


# Run with: uvicorn api.main:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
