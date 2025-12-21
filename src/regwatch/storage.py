"""
Document storage abstraction for regwatch.

Supports both local filesystem (development) and S3-compatible storage (Railway).
Automatically detects Railway bucket environment variables and uses S3 when available.
"""

import logging
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

# Load .env file for local development (no-op if file doesn't exist)
load_dotenv()
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


# =============================================================================
# Storage Mode Detection
# =============================================================================

# Force local storage in development (set USE_LOCAL_STORAGE=1 in .env)
USE_LOCAL_STORAGE = os.getenv("USE_LOCAL_STORAGE", "").lower() in ("1", "true", "yes")

# Detect Railway environment (Railway injects this env var)
IS_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT"))


# =============================================================================
# S3 Configuration (Railway Bucket environment variables)
# =============================================================================

S3_BUCKET = os.getenv("BUCKET")
S3_ACCESS_KEY = os.getenv("ACCESS_KEY_ID")
S3_SECRET_KEY = os.getenv("SECRET_ACCESS_KEY")
S3_ENDPOINT = os.getenv("ENDPOINT", "https://storage.railway.app")
S3_REGION = os.getenv("REGION", "auto")

# S3 key prefix for regwatch documents
S3_PREFIX = "regwatch/cache"

# Local fallback cache directory
LOCAL_CACHE_DIR = Path("output/regwatch/cache")


def _build_key(subfolder: str | None, key: str) -> str:
    """Build a storage key with optional subfolder.

    Args:
        subfolder: Optional subfolder (e.g., feed topic like "DORA", "MiCA")
        key: Document identifier (e.g., CELEX number)

    Returns:
        Full key path: "{subfolder}/{key}" or just "{key}"
    """
    if subfolder:
        return f"{subfolder}/{key}"
    return key


def is_s3_configured() -> bool:
    """
    Check if S3 storage should be used.

    Returns True when:
    - Running on Railway (RAILWAY_ENVIRONMENT is set), AND
    - S3 credentials are available

    Returns False when:
    - USE_LOCAL_STORAGE is set (forces local storage in development)
    - Not running on Railway
    - S3 credentials are missing
    """
    # Force local storage if explicitly requested
    if USE_LOCAL_STORAGE:
        return False

    # Only use S3 when running on Railway
    if not IS_RAILWAY:
        return False

    # Check if S3 credentials are available
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

    def read(self, key: str, subfolder: str | None = None) -> str | None:
        """
        Read document content by key.

        Args:
            key: Document identifier (e.g., CELEX number)
            subfolder: Optional subfolder (e.g., feed topic like "DORA")

        Returns:
            Document content as string, or None if not found
        """
        full_key = _build_key(subfolder, key)
        if self.use_s3:
            return self._read_s3(full_key)
        return self._read_local(full_key)

    def write(self, key: str, content: str, subfolder: str | None = None) -> bool:
        """
        Write document content.

        Args:
            key: Document identifier
            content: Document content to store
            subfolder: Optional subfolder (e.g., feed topic like "DORA")

        Returns:
            True if successful, False otherwise
        """
        full_key = _build_key(subfolder, key)
        if self.use_s3:
            return self._write_s3(full_key, content)
        return self._write_local(full_key, content)

    def exists(self, key: str, subfolder: str | None = None) -> bool:
        """Check if document exists in storage."""
        full_key = _build_key(subfolder, key)
        if self.use_s3:
            return self._exists_s3(full_key)
        return self._exists_local(full_key)

    def delete(self, key: str, subfolder: str | None = None) -> bool:
        """Delete document from storage."""
        full_key = _build_key(subfolder, key)
        if self.use_s3:
            return self._delete_s3(full_key)
        return self._delete_local(full_key)

    def list_keys(self, prefix: str, subfolder: str | None = None) -> list[str]:
        """
        List all keys matching a prefix.

        Args:
            prefix: Key prefix to match (e.g., "weekly_summary_")
            subfolder: Optional subfolder

        Returns:
            List of matching keys (without .txt extension)
        """
        full_prefix = _build_key(subfolder, prefix)
        if self.use_s3:
            return self._list_keys_s3(full_prefix)
        return self._list_keys_local(full_prefix)

    # -------------------------------------------------------------------------
    # S3 Implementation
    # -------------------------------------------------------------------------

    def _read_s3(self, key: str) -> str | None:
        """Read document from S3."""
        s3_key = f"{S3_PREFIX}/{key}.txt"
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
        s3_key = f"{S3_PREFIX}/{key}.txt"
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
        s3_key = f"{S3_PREFIX}/{key}.txt"
        try:
            self.s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
            return True
        except ClientError:
            return False

    def _delete_s3(self, key: str) -> bool:
        """Delete document from S3."""
        s3_key = f"{S3_PREFIX}/{key}.txt"
        try:
            self.s3_client.delete_object(Bucket=S3_BUCKET, Key=s3_key)
            logger.debug(f"S3 delete: {s3_key}")
            return True
        except ClientError as e:
            logger.error(f"S3 delete error for {s3_key}: {e}")
            return False

    def _list_keys_s3(self, prefix: str) -> list[str]:
        """List all keys matching a prefix in S3."""
        s3_prefix = f"{S3_PREFIX}/{prefix}"
        keys = []
        try:
            paginator = self.s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=s3_prefix):
                for obj in page.get("Contents", []):
                    # Extract key without prefix and .txt extension
                    key = obj["Key"]
                    if key.startswith(S3_PREFIX + "/"):
                        key = key[len(S3_PREFIX) + 1:]
                    if key.endswith(".txt"):
                        key = key[:-4]
                    keys.append(key)
            logger.debug(f"S3 list: prefix={prefix}, found {len(keys)} keys")
            return keys
        except ClientError as e:
            logger.error(f"S3 list error for prefix {prefix}: {e}")
            return []

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
            # Create parent directories if they don't exist (for subfolder support)
            file_path.parent.mkdir(parents=True, exist_ok=True)
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

    def _list_keys_local(self, prefix: str) -> list[str]:
        """List all keys matching a prefix locally."""
        keys = []
        # Handle prefix with subfolders (e.g., "DORA/32022R")
        if "/" in prefix:
            subfolder, file_prefix = prefix.rsplit("/", 1)
            search_dir = LOCAL_CACHE_DIR / subfolder
        else:
            file_prefix = prefix
            search_dir = LOCAL_CACHE_DIR

        if search_dir.exists():
            for file_path in search_dir.glob(f"{file_prefix}*.txt"):
                # Return key relative to LOCAL_CACHE_DIR without .txt
                relative = file_path.relative_to(LOCAL_CACHE_DIR)
                key = str(relative).replace(".txt", "")
                keys.append(key)
        logger.debug(f"Local list: prefix={prefix}, found {len(keys)} keys")
        return keys


# Global storage instance (lazy initialization)
_storage: DocumentStorage | None = None


def get_storage() -> DocumentStorage:
    """Get the global document storage instance."""
    global _storage
    if _storage is None:
        _storage = DocumentStorage()
    return _storage
