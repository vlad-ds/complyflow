"""
Pytest fixtures for API testing.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Set test environment before importing app
os.environ["AIRTABLE_API_KEY"] = "test_key"
os.environ["AIRTABLE_BASE_ID"] = "test_base"

# Import the app module after setting env vars
import api.main as api_main


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Load a sample PDF for testing."""
    pdf_path = Path("cuad/train/contracts/01_service_gpaq.pdf")
    if pdf_path.exists():
        return pdf_path.read_bytes()
    # Return minimal valid PDF if test file doesn't exist
    return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000058 00000 n\n0000000115 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"


@pytest.fixture
def mock_extraction_result() -> dict:
    """Mock extraction result."""
    return {
        "extraction": {
            "parties": {
                "raw_snippet": "GPAQ and Service Provider",
                "normalized_value": ["GPAQ Acquisition Holdings", "Service Provider Inc."],
            },
            "contract_type": {
                "raw_snippet": "Service Agreement",
                "normalized_value": "Service Agreement",
            },
            "agreement_date": {
                "raw_snippet": "January 1, 2020",
                "normalized_value": "2020-01-01",
            },
            "effective_date": {
                "raw_snippet": "January 1, 2020",
                "normalized_value": "2020-01-01",
            },
            "expiration_date": {
                "raw_snippet": "December 31, 2025",
                "normalized_value": "2025-12-31",
            },
            "notice_period": {
                "raw_snippet": "30 days",
                "normalized_value": "30 days",
            },
            "renewal_term": {
                "raw_snippet": "1 year",
                "normalized_value": "1 year",
            },
            "governing_law": {
                "raw_snippet": "State of Delaware",
                "normalized_value": "Delaware",
            },
        },
        "computed_dates": {
            "agreement_date": {"year": 2020, "month": 1, "day": 1},
            "effective_date": {"year": 2020, "month": 1, "day": 1},
            "expiration_date": {"year": 2025, "month": 12, "day": 31},
            "notice_deadline": {"year": 2025, "month": 12, "day": 1},
            "first_renewal_date": {"year": 2025, "month": 12, "day": 31},
        },
        "usage": {
            "extraction": {
                "model": "gpt-5-mini-2025-08-07",
                "input_tokens": 5000,
                "output_tokens": 500,
            },
            "date_computation": {
                "model": "gpt-5-mini-2025-08-07",
                "input_tokens": 1000,
                "output_tokens": 200,
                "latency_seconds": 1.5,
            },
        },
    }


@pytest.fixture
def mock_airtable_record() -> dict:
    """Mock Airtable record response."""
    return {
        "id": "rec123456789",
        "fields": {
            "filename": "test_contract.pdf",
            "parties": '["Party A", "Party B"]',
            "contract_type": "services",
            "status": "under_review",
        },
        "createdTime": "2025-01-01T00:00:00.000Z",
    }


@pytest.fixture
def mock_airtable_service(mock_airtable_record):
    """Mock AirtableService."""
    mock = MagicMock()
    mock.create_contract.return_value = mock_airtable_record
    mock.get_contract.return_value = mock_airtable_record
    mock.list_contracts.return_value = [mock_airtable_record]
    mock.get_airtable_url.return_value = "https://airtable.com/test_base/Contracts/rec123456789"
    mock.mark_reviewed.return_value = {
        **mock_airtable_record,
        "fields": {**mock_airtable_record["fields"], "status": "reviewed"},
    }
    return mock


@pytest.fixture
def client(mock_airtable_service):
    """
    Test client with mocked dependencies.

    Mocks:
    - AirtableService (no real Airtable calls)
    - process_contract (no real LLM calls)
    - notify_new_contract (no real Slack calls)
    """
    with patch.object(api_main, "get_airtable", return_value=mock_airtable_service):
        yield TestClient(api_main.app)


@pytest.fixture
def client_with_extraction(mock_airtable_service, mock_extraction_result):
    """
    Test client with mocked extraction pipeline.

    Use this for testing the full upload flow without real LLM calls.
    """
    with patch.object(api_main, "get_airtable", return_value=mock_airtable_service):
        with patch.object(api_main, "process_contract", return_value={
            "filename": "test.pdf",
            **mock_extraction_result,
        }):
            with patch.object(api_main, "notify_new_contract", return_value=None):
                yield TestClient(api_main.app)
