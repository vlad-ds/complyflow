"""
Tests for regulatory document metadata parsing.
"""

from datetime import date

import pytest

from regwatch.metadata import (
    parse_celex,
    parse_document_header,
    extract_metadata,
    DocumentMetadata,
    CELEX_SECTORS,
    CELEX_DOC_TYPES,
)


class TestParseCelex:
    """Tests for CELEX number parsing."""

    def test_regulation_dora(self):
        """Parse DORA regulation CELEX: 32022R2554."""
        result = parse_celex("32022R2554")
        assert result["sector"] == "3"
        assert result["sector_name"] == "legislation"
        assert result["year"] == 2022
        assert result["type_code"] == "R"
        assert result["type_name"] == "regulation"
        assert result["serial"] == "2554"
        assert result["is_final"] is True

    def test_directive(self):
        """Parse a directive CELEX: 32014L0065 (MiFID II)."""
        result = parse_celex("32014L0065")
        assert result["sector_name"] == "legislation"
        assert result["year"] == 2014
        assert result["type_code"] == "L"
        assert result["type_name"] == "directive"
        assert result["is_final"] is True

    def test_decision(self):
        """Parse a decision CELEX: 32020D0001."""
        result = parse_celex("32020D0001")
        assert result["type_code"] == "D"
        assert result["type_name"] == "decision"

    def test_proposal(self):
        """Parse a proposal CELEX: 52025PC0837."""
        result = parse_celex("52025PC0837")
        assert result["sector"] == "5"
        assert result["sector_name"] == "preparatory_acts"
        assert result["year"] == 2025
        assert result["type_code"] == "PC"
        assert result["type_name"] == "proposal_com"
        assert result["is_final"] is False

    def test_oj_c_series_slash(self):
        """Parse OJ C series: C/2025/05391."""
        result = parse_celex("C/2025/05391")
        assert result["sector"] == "C"
        assert result["sector_name"] == "oj_c_series"
        assert result["year"] == 2025
        assert result["serial"] == "05391"

    def test_oj_c_series_underscore(self):
        """Parse OJ C series with underscore: C_2025_05391."""
        result = parse_celex("C_2025_05391")
        assert result["sector"] == "C"
        assert result["year"] == 2025

    def test_unknown_format_fallback(self):
        """Unknown format should extract year if possible."""
        result = parse_celex("UNKNOWN2024FORMAT")
        assert result["year"] == 2024
        assert result["sector"] == "unknown"


class TestParseDocumentHeader:
    """Tests for document header parsing."""

    def test_parliament_council_regulation(self):
        """Parse regulation from European Parliament and Council."""
        header = """REGULATION (EU) 2022/2554 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL
of 14 December 2022
on digital operational resilience for the financial sector

(Text with EEA relevance)
"""
        result = parse_document_header(header)
        assert result["legal_basis"] == "parliament_council"
        assert result["adopted_date"] == date(2022, 12, 14)
        assert "digital operational resilience" in result["short_subject"]

    def test_commission_delegated_regulation(self):
        """Parse Commission Delegated Regulation."""
        header = """COMMISSION DELEGATED REGULATION (EU) 2024/1234
of 5 March 2024
supplementing Regulation (EU) 2022/2554
"""
        result = parse_document_header(header)
        assert result["legal_basis"] == "commission_delegated"
        assert result["adopted_date"] == date(2024, 3, 5)

    def test_commission_implementing_regulation(self):
        """Parse Commission Implementing Regulation."""
        header = """COMMISSION IMPLEMENTING REGULATION (EU) 2024/5678
of 10 January 2024
laying down technical standards
"""
        result = parse_document_header(header)
        assert result["legal_basis"] == "commission_implementing"

    def test_no_header_info(self):
        """Empty or irrelevant header should return None values."""
        result = parse_document_header("")
        assert result["legal_basis"] is None
        assert result["adopted_date"] is None


class TestExtractMetadata:
    """Tests for complete metadata extraction."""

    def test_full_metadata(self):
        """Extract metadata with all sources."""
        content = """REGULATION (EU) 2022/2554 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL
of 14 December 2022
on digital operational resilience for the financial sector
"""
        metadata = extract_metadata(
            celex="32022R2554",
            content=content,
            topic="DORA",
            publication_date=date(2022, 12, 27),
            title="Digital Operational Resilience Act",
            url="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2554",
        )

        assert isinstance(metadata, DocumentMetadata)
        assert metadata.celex == "32022R2554"
        assert metadata.topic == "DORA"
        assert metadata.doc_type == "regulation"
        assert metadata.year == 2022
        assert metadata.is_final is True
        assert metadata.legal_basis == "parliament_council"
        assert metadata.adopted_date == date(2022, 12, 14)

    def test_metadata_without_content(self):
        """Extract metadata without document content."""
        metadata = extract_metadata(
            celex="32022R2554",
            content=None,
            topic="DORA",
        )

        assert metadata.celex == "32022R2554"
        assert metadata.topic == "DORA"
        assert metadata.legal_basis is None  # No content to parse

    def test_to_chunk_metadata(self):
        """Convert metadata to chunk payload format."""
        metadata = DocumentMetadata(
            celex="32022R2554",
            sector="legislation",
            year=2022,
            doc_type="regulation",
            serial="2554",
            is_final=True,
            topic="DORA",
            title="DORA Regulation",
        )

        chunk_meta = metadata.to_chunk_metadata(chunk_index=0, source_file="DORA/32022R2554.txt")

        assert chunk_meta["doc_id"] == "32022R2554"
        assert chunk_meta["chunk_index"] == 0
        assert chunk_meta["source_file"] == "DORA/32022R2554.txt"
        assert chunk_meta["topic"] == "DORA"
        assert chunk_meta["is_final"] is True
