"""
Document storage abstraction for regwatch.

Supports both local filesystem (development) and S3-compatible storage (Railway).
Automatically detects Railway bucket environment variables and uses S3 when available.
"""

import logging
import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


# =============================================================================
# S3 Configuration (Railway Bucket environment variables)
# =============================================================================

S3_BUCKET = os.getenv("BUCKET")
S3_ACCESS_KEY = os.getenv("ACCESS_KEY_ID")
S3_SECRET_KEY = os.getenv("SECRET_ACCESS_KEY")
S3_ENDPOINT = os.getenv("ENDPOINT", "https://storage.railway.app")
S3_REGION = os.getenv("REGION", "auto")

# S3 key prefix for regwatch documents
S3_PREFIX = "regwatch/cache/"

# Local fallback cache directory
LOCAL_CACHE_DIR = Path("output/regwatch/cache")


def is_s3_configured() -> bool:
    """Check if S3 storage is configured (Railway bucket environment)."""
    return all([S3_BUCKET, S3_ACCESS_KEY, S3_SECRET_KEY])


def get_s3_client():
    """Create and return an S3 client for Railway bucket."""
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        region_name=S3_REGION,
    )


class DocumentStorage:
    """
    Unified document storage interface.

    Uses S3 when Railway bucket is configured, otherwise falls back to local filesystem.
    """

    def __init__(self):
        self.use_s3 = is_s3_configured()

        if self.use_s3:
            self.s3_client = get_s3_client()
            logger.info(f"Using S3 storage: bucket={S3_BUCKET}")
        else:
            LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using local storage: {LOCAL_CACHE_DIR}")

    def read(self, key: str) -> str | None:
        """
        Read document content by key.

        Args:
            key: Document identifier (e.g., CELEX number)

        Returns:
            Document content as string, or None if not found
        """
        if self.use_s3:
            return self._read_s3(key)
        return self._read_local(key)

    def write(self, key: str, content: str) -> bool:
        """
        Write document content.

        Args:
            key: Document identifier
            content: Document content to store

        Returns:
            True if successful, False otherwise
        """
        if self.use_s3:
            return self._write_s3(key, content)
        return self._write_local(key, content)

    def exists(self, key: str) -> bool:
        """Check if document exists in storage."""
        if self.use_s3:
            return self._exists_s3(key)
        return self._exists_local(key)

    def delete(self, key: str) -> bool:
        """Delete document from storage."""
        if self.use_s3:
            return self._delete_s3(key)
        return self._delete_local(key)

    # -------------------------------------------------------------------------
    # S3 Implementation
    # -------------------------------------------------------------------------

    def _read_s3(self, key: str) -> str | None:
        """Read document from S3."""
        s3_key = f"{S3_PREFIX}{key}.txt"
        try:
            response = self.s3_client.get_object(Bucket=S3_BUCKET, Key=s3_key)
            content = response["Body"].read().decode("utf-8")
            logger.debug(f"S3 read: {s3_key} ({len(content)} chars)")
            return content
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return None
            logger.error(f"S3 read error for {s3_key}: {e}")
            return None

    def _write_s3(self, key: str, content: str) -> bool:
        """Write document to S3."""
        s3_key = f"{S3_PREFIX}{key}.txt"
        try:
            self.s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=s3_key,
                Body=content.encode("utf-8"),
                ContentType="text/plain; charset=utf-8",
            )
            logger.debug(f"S3 write: {s3_key} ({len(content)} chars)")
            return True
        except ClientError as e:
            logger.error(f"S3 write error for {s3_key}: {e}")
            return False

    def _exists_s3(self, key: str) -> bool:
        """Check if document exists in S3."""
        s3_key = f"{S3_PREFIX}{key}.txt"
        try:
            self.s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
            return True
        except ClientError:
            return False

    def _delete_s3(self, key: str) -> bool:
        """Delete document from S3."""
        s3_key = f"{S3_PREFIX}{key}.txt"
        try:
            self.s3_client.delete_object(Bucket=S3_BUCKET, Key=s3_key)
            logger.debug(f"S3 delete: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"S3 delete error for {s3_key}: {e}")
            return False

    # -------------------------------------------------------------------------
    # Local Filesystem Implementation
    # -------------------------------------------------------------------------

    def _read_local(self, key: str) -> str | None:
        """Read document from local filesystem."""
        file_path = LOCAL_CACHE_DIR / f"{key}.txt"
        if file_path.exists():
            content = file_path.read_text()
            logger.debug(f"Local read: {file_path} ({len(content)} chars)")
            return content
        return None

    def _write_local(self, key: str, content: str) -> bool:
        """Write document to local filesystem."""
        file_path = LOCAL_CACHE_DIR / f"{key}.txt"
        try:
            file_path.write_text(content)
            logger.debug(f"Local write: {file_path} ({len(content)} chars)")
            return True
        except Exception as e:
            logger.error(f"Local write error for {file_path}: {e}")
            return False

    def _exists_local(self, key: str) -> bool:
        """Check if document exists locally."""
        return (LOCAL_CACHE_DIR / f"{key}.txt").exists()

    def _delete_local(self, key: str) -> bool:
        """Delete document from local filesystem."""
        file_path = LOCAL_CACHE_DIR / f"{key}.txt"
        try:
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Local delete: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Local delete error for {file_path}: {e}")
            return False


# Global storage instance (lazy initialization)
_storage: DocumentStorage | None = None


def get_storage() -> DocumentStorage:
    """Get the global document storage instance."""
    global _storage
    if _storage is None:
        _storage = DocumentStorage()
    return _storage
