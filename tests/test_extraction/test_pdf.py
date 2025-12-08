"""
Tests for PDF text extraction.
"""

from pathlib import Path

import pytest

from extraction.pdf_text import extract_text_from_pdf, extract_text_by_page


# Path to sample contracts
CUAD_TRAIN_DIR = Path("cuad/train/contracts")
SAMPLE_PDF = CUAD_TRAIN_DIR / "01_service_gpaq.pdf"


@pytest.fixture
def sample_pdf_path():
    """Return path to sample PDF if it exists."""
    if SAMPLE_PDF.exists():
        return SAMPLE_PDF
    pytest.skip("Sample PDF not found - run from project root")


class TestExtractTextFromPdf:
    """Tests for extract_text_from_pdf function."""

    def test_extracts_text(self, sample_pdf_path):
        """Should extract text from PDF."""
        text = extract_text_from_pdf(sample_pdf_path)

        assert isinstance(text, str)
        assert len(text) > 1000  # Should have substantial content

    def test_contains_expected_content(self, sample_pdf_path):
        """Extracted text should contain contract content."""
        text = extract_text_from_pdf(sample_pdf_path)

        # GPAQ service agreement should have some identifiable terms
        text_lower = text.lower()
        assert any(
            term in text_lower
            for term in ["agreement", "parties", "services", "contract"]
        )

    def test_path_as_string(self, sample_pdf_path):
        """Should accept path as string."""
        text = extract_text_from_pdf(str(sample_pdf_path))
        assert len(text) > 0

    def test_nonexistent_file(self):
        """Should raise error for nonexistent file."""
        with pytest.raises(Exception):
            extract_text_from_pdf("nonexistent_file.pdf")


class TestExtractTextByPage:
    """Tests for extract_text_by_page function."""

    def test_returns_list(self, sample_pdf_path):
        """Should return list of page texts."""
        pages = extract_text_by_page(sample_pdf_path)

        assert isinstance(pages, list)
        assert len(pages) > 0

    def test_all_pages_are_strings(self, sample_pdf_path):
        """Each page should be a string."""
        pages = extract_text_by_page(sample_pdf_path)

        for page in pages:
            assert isinstance(page, str)

    def test_page_count_reasonable(self, sample_pdf_path):
        """Contract should have reasonable number of pages."""
        pages = extract_text_by_page(sample_pdf_path)

        # A typical contract has multiple pages
        assert len(pages) >= 1
        assert len(pages) < 500  # But not unreasonably many
