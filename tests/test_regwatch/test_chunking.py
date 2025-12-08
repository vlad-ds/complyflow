"""
Tests for document chunking utilities.
"""

import pytest

from regwatch.chunking import format_metadata_header
from regwatch.metadata import DocumentMetadata


class TestFormatMetadataHeader:
    """Tests for metadata header formatting."""

    def test_full_metadata(self):
        """Format header with all metadata fields."""
        metadata = DocumentMetadata(
            celex="32022R2554",
            sector="legislation",
            year=2022,
            doc_type="regulation",
            serial="2554",
            is_final=True,
            topic="DORA",
            title="Digital Operational Resilience Act",
            short_subject="on digital operational resilience for the financial sector",
        )

        header = format_metadata_header(metadata)

        assert "CELEX: 32022R2554" in header
        assert "Topic: DORA" in header
        assert "Type: regulation" in header
        assert "Title: Digital Operational Resilience Act" in header
        assert "Subject: on digital operational resilience" in header
        assert "---" in header

    def test_minimal_metadata(self):
        """Format header with minimal metadata."""
        metadata = DocumentMetadata(
            celex="32022R2554",
            sector="legislation",
            year=2022,
            doc_type="regulation",
            serial="2554",
            is_final=True,
        )

        header = format_metadata_header(metadata)

        assert "CELEX: 32022R2554" in header
        assert "Type: regulation" in header
        # No topic or title
        assert "Topic:" not in header

    def test_no_duplicate_title_subject(self):
        """Subject should not duplicate title."""
        metadata = DocumentMetadata(
            celex="32022R2554",
            sector="legislation",
            year=2022,
            doc_type="regulation",
            serial="2554",
            is_final=True,
            title="DORA",
            short_subject="DORA",  # Same as title
        )

        header = format_metadata_header(metadata)

        # Title should appear once, subject should be skipped
        assert header.count("DORA") == 1

    def test_empty_metadata(self):
        """Format header with no optional metadata."""
        metadata = DocumentMetadata(
            celex="",  # Empty CELEX
            sector="unknown",
            year=0,
            doc_type="",
            serial="",
            is_final=False,
        )

        header = format_metadata_header(metadata)

        # Should return empty string for completely empty metadata
        assert header == ""

    def test_header_ends_with_separator(self):
        """Header should end with separator and newline."""
        metadata = DocumentMetadata(
            celex="32022R2554",
            sector="legislation",
            year=2022,
            doc_type="regulation",
            serial="2554",
            is_final=True,
            topic="DORA",
        )

        header = format_metadata_header(metadata)

        assert header.endswith("---\n")
