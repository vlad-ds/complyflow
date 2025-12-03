"""
Tests for the Contract Intake API endpoints.
"""

import pytest


class TestHealth:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestUploadContract:
    """Tests for POST /contracts/upload endpoint."""

    def test_upload_requires_file(self, client):
        response = client.post("/contracts/upload")
        assert response.status_code == 422  # Validation error

    def test_upload_rejects_non_pdf(self, client):
        response = client.post(
            "/contracts/upload",
            files={"file": ("test.txt", b"not a pdf", "text/plain")},
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]
        assert ".txt" in response.json()["detail"]

    def test_upload_rejects_empty_file(self, client_with_extraction):
        response = client_with_extraction.post(
            "/contracts/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_upload_rejects_file_without_extension(self, client):
        response = client.post(
            "/contracts/upload",
            files={"file": ("noextension", b"content", "application/octet-stream")},
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_upload_success(self, client_with_extraction, sample_pdf_bytes):
        response = client_with_extraction.post(
            "/contracts/upload",
            files={"file": ("contract.pdf", sample_pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "contract_id" in data
        assert data["contract_id"] == "rec123456789"
        assert data["status"] == "under_review"
        assert "extraction" in data
        assert "computed_dates" in data
        assert "airtable_url" in data

    def test_upload_returns_extraction_data(self, client_with_extraction, sample_pdf_bytes):
        response = client_with_extraction.post(
            "/contracts/upload",
            files={"file": ("contract.pdf", sample_pdf_bytes, "application/pdf")},
        )
        data = response.json()

        # Check extraction fields
        extraction = data["extraction"]
        assert "parties" in extraction
        assert "contract_type" in extraction
        assert "agreement_date" in extraction

    def test_upload_returns_computed_dates(self, client_with_extraction, sample_pdf_bytes):
        response = client_with_extraction.post(
            "/contracts/upload",
            files={"file": ("contract.pdf", sample_pdf_bytes, "application/pdf")},
        )
        data = response.json()

        # Check computed dates
        dates = data["computed_dates"]
        assert "agreement_date" in dates
        assert "effective_date" in dates
        assert "expiration_date" in dates
        assert "notice_deadline" in dates


class TestGetContract:
    """Tests for GET /contracts/{record_id} endpoint."""

    def test_get_contract_success(self, client):
        response = client.get("/contracts/rec123456789")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "rec123456789"
        assert "fields" in data

    def test_get_contract_not_found(self, client, mock_airtable_service):
        mock_airtable_service.get_contract.return_value = None
        response = client.get("/contracts/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestListContracts:
    """Tests for GET /contracts endpoint."""

    def test_list_contracts_success(self, client):
        response = client.get("/contracts")
        assert response.status_code == 200
        data = response.json()
        assert "contracts" in data
        assert "total" in data
        assert isinstance(data["contracts"], list)

    def test_list_contracts_with_status_filter(self, client):
        response = client.get("/contracts?status=under_review")
        assert response.status_code == 200

    def test_list_contracts_invalid_status(self, client):
        response = client.get("/contracts?status=invalid")
        assert response.status_code == 400
        assert "under_review" in response.json()["detail"]

    def test_list_contracts_with_limit(self, client):
        response = client.get("/contracts?limit=10")
        assert response.status_code == 200


class TestReviewContract:
    """Tests for PATCH /contracts/{record_id}/review endpoint."""

    def test_review_contract_success(self, client):
        response = client.patch(
            "/contracts/rec123456789/review",
            json={"reviewed": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reviewed"

    def test_unreview_contract(self, client, mock_airtable_service):
        mock_airtable_service.update_contract.return_value = {
            "id": "rec123456789",
            "fields": {"status": "under_review"},
        }
        response = client.patch(
            "/contracts/rec123456789/review",
            json={"reviewed": False},
        )
        assert response.status_code == 200

    def test_review_not_found(self, client, mock_airtable_service):
        mock_airtable_service.get_contract.return_value = None
        response = client.patch(
            "/contracts/nonexistent/review",
            json={"reviewed": True},
        )
        assert response.status_code == 404
