"""
ComplyFlow Contract Intake API.

FastAPI server for contract upload, metadata extraction, and Airtable storage.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from dotenv import load_dotenv

# Load environment variables before other imports
load_dotenv()

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from api.models import (
    ContractListResponse,
    ContractRecord,
    ContractReviewRequest,
    ContractReviewResponse,
    ContractUploadResponse,
    ErrorResponse,
    HealthResponse,
)
from api.services.airtable import AirtableService
from api.services.extraction import process_contract
from api.services.slack import notify_new_contract


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
    # Initialize Airtable service
    global _airtable
    try:
        _airtable = AirtableService()
        print("Airtable service initialized")
    except Exception as e:
        print(f"Warning: Could not initialize Airtable: {e}")

    yield

    # Cleanup on shutdown
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
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    tags=["Contracts"],
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
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Read file content
    try:
        pdf_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    # Process contract (extraction + date computation)
    try:
        contract_data = process_contract(pdf_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

    # Store in Airtable
    try:
        airtable = get_airtable()
        record = airtable.create_contract(contract_data)
        record_id = record["id"]
        airtable_url = airtable.get_airtable_url(record_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Airtable storage failed: {e}")

    # Send Slack notification (fire and forget, don't fail if Slack fails)
    try:
        await notify_new_contract(contract_data, record_id, airtable_url)
    except Exception as e:
        print(f"Slack notification failed (non-fatal): {e}")

    return ContractUploadResponse(
        contract_id=record_id,
        filename=file.filename,
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
    responses={404: {"model": ErrorResponse}},
    tags=["Contracts"],
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


@app.patch(
    "/contracts/{record_id}/review",
    response_model=ContractReviewResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["Contracts"],
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


@app.get(
    "/contracts",
    response_model=ContractListResponse,
    tags=["Contracts"],
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
