"""
PDF storage service for contract files.

Stores PDFs in Railway S3-compatible bucket (production) or local filesystem (development).
Mirrors the pattern from regwatch/storage.py but handles binary PDF files.
"""

import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# =============================================================================
# Storage Configuration
# =============================================================================

# Force local storage in development
USE_LOCAL_STORAGE = os.getenv("USE_LOCAL_STORAGE", "").lower() in ("1", "true", "yes")

# Detect Railway environment
IS_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT"))

# S3 Configuration (Railway Bucket)
S3_BUCKET = os.getenv("BUCKET")
S3_ACCESS_KEY = os.getenv("ACCESS_KEY_ID")
S3_SECRET_KEY = os.getenv("SECRET_ACCESS_KEY")
S3_ENDPOINT = os.getenv("ENDPOINT", "https://storage.railway.app")
S3_REGION = os.getenv("REGION", "auto")

# S3 key prefix for contract PDFs
S3_PREFIX = "contracts/pdfs"

# Local fallback directory
LOCAL_PDF_DIR = Path("output/contracts/pdfs")


def _is_s3_configured() -> bool:
    """Check if S3 storage should be used."""
    if USE_LOCAL_STORAGE:
        return False
    if not IS_RAILWAY:
        return False
    return all([S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY])


def _get_s3_client():
    """Create S3 client for Railway bucket."""
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
    )


class PDFStorage:
    """
    PDF storage interface.

    Uses S3 on Railway, local filesystem in development.
    """

    def __init__(self):
        self.use_s3 = _is_s3_configured()

        if self.use_s3:
            self.s3_client = _get_s3_client()
            logger.info(f"PDF storage using S3: bucket={S3_BUCKET}, prefix={S3_PREFIX}")
        else:
            LOCAL_PDF_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"PDF storage using local: {LOCAL_PDF_DIR}")

    def store(self, contract_id: str, filename: str, pdf_bytes: bytes) -> str:
        """
        Store a PDF file.

        Args:
            contract_id: Airtable record ID (e.g., "recXXX")
            filename: Original filename (for reference)
            pdf_bytes: PDF file content

        Returns:
            Storage path that can be used to retrieve the file
        """
        # Use contract_id as the key to ensure uniqueness
        # Keep original filename in a separate part for display purposes
        key = f"{contract_id}.pdf"

        if self.use_s3:
            return self._store_s3(key, pdf_bytes, filename)
        return self._store_local(key, pdf_bytes)

    def retrieve(self, contract_id: str) -> bytes | None:
        """
        Retrieve a PDF file.

        Args:
            contract_id: Airtable record ID

        Returns:
            PDF bytes, or None if not found
        """
        key = f"{contract_id}.pdf"

        if self.use_s3:
            return self._retrieve_s3(key)
        return self._retrieve_local(key)

    def exists(self, contract_id: str) -> bool:
        """Check if a PDF exists for a contract."""
        key = f"{contract_id}.pdf"

        if self.use_s3:
            return self._exists_s3(key)
        return self._exists_local(key)

    def delete(self, contract_id: str) -> bool:
        """Delete a PDF file."""
        key = f"{contract_id}.pdf"

        if self.use_s3:
            return self._delete_s3(key)
        return self._delete_local(key)

    def get_storage_path(self, contract_id: str) -> str:
        """
        Get the storage path/URL for a contract PDF.

        For S3: returns the S3 key (not a public URL - PDFs are served via API)
        For local: returns the local file path
        """
        key = f"{contract_id}.pdf"

        if self.use_s3:
            return f"{S3_PREFIX}/{key}"
        return str(LOCAL_PDF_DIR / key)

    # -------------------------------------------------------------------------
    # S3 Implementation
    # -------------------------------------------------------------------------

    def _store_s3(self, key: str, pdf_bytes: bytes, original_filename: str) -> str:
        """Store PDF in S3."""
        s3_key = f"{S3_PREFIX}/{key}"
        try:
            self.s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=pdf_bytes,
                ContentType="application/pdf",
                Metadata={"original-filename": original_filename},
            )
            logger.info(f"S3 store: {s3_key} ({len(pdf_bytes)} bytes)")
            return s3_key
        except ClientError as e:
            logger.error(f"S3 store error for {s3_key}: {e}")
            raise

    def _retrieve_s3(self, key: str) -> bytes | None:
        """Retrieve PDF from S3."""
        s3_key = f"{S3_PREFIX}/{key}"
        try:
            response = self.s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
            pdf_bytes = response["Body"].read()
            logger.debug(f"S3 retrieve: {s3_key} ({len(pdf_bytes)} bytes)")
            return pdf_bytes
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            logger.error(f"S3 retrieve error for {s3_key}: {e}")
            return None

    def _exists_s3(self, key: str) -> bool:
        """Check if PDF exists in S3."""
        s3_key = f"{S3_PREFIX}/{key}"
        try:
            self.s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
            return True
        except ClientError:
            return False

    def _delete_s3(self, key: str) -> bool:
        """Delete PDF from S3."""
        s3_key = f"{S3_PREFIX}/{key}"
        try:
            self.s3_client.delete_object(Bucket=S3_BUCKET, Key=s3_key)
            logger.info(f"S3 delete: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"S3 delete error for {s3_key}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Local Implementation
    # -------------------------------------------------------------------------

    def _store_local(self, key: str, pdf_bytes: bytes) -> str:
        """Store PDF locally."""
        file_path = LOCAL_PDF_DIR / key
        try:
            file_path.write_bytes(pdf_bytes)
            logger.info(f"Local store: {file_path} ({len(pdf_bytes)} bytes)")
            return str(file_path)
        except Exception as e:
            logger.error(f"Local store error for {file_path}: {e}")
            raise

    def _retrieve_local(self, key: str) -> bytes | None:
        """Retrieve PDF from local storage."""
        file_path = LOCAL_PDF_DIR / key
        if file_path.exists():
            pdf_bytes = file_path.read_bytes()
            logger.debug(f"Local retrieve: {file_path} ({len(pdf_bytes)} bytes)")
            return pdf_bytes
        return None

    def _exists_local(self, key: str) -> bool:
        """Check if PDF exists locally."""
        return (LOCAL_PDF_DIR / key).exists()

    def _delete_local(self, key: str) -> bool:
        """Delete PDF from local storage."""
        file_path = LOCAL_PDF_DIR / key
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Local delete: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Local delete error for {file_path}: {e}")
            return False


# Global instance (lazy initialization)
_pdf_storage: PDFStorage | None = None


def get_pdf_storage() -> PDFStorage:
    """Get the global PDF storage instance."""
    global _pdf_storage
    if _pdf_storage is None:
        _pdf_storage = PDFStorage()
    return _pdf_storage
