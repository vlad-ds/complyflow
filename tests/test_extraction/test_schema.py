"""
Tests for extraction schema models.
"""

import pytest
from pydantic import ValidationError

from extraction.schema import (
    ContractType,
    DateField,
    DateComputationResult,
    SpecialDateValue,
    ExtractedFieldBase,
    PartiesExtraction,
)


class TestContractType:
    """Tests for ContractType enum."""

    def test_all_types_have_values(self):
        """All contract types should have string values."""
        for ct in ContractType:
            assert isinstance(ct.value, str)
            assert len(ct.value) > 0

    def test_license_type(self):
        """License Agreement type should exist."""
        assert ContractType.LICENSE.value == "License Agreement"

    def test_service_type(self):
        """Service Agreement type should exist."""
        assert ContractType.SERVICE.value == "Service Agreement"

    def test_enum_count(self):
        """Should have expected number of contract types."""
        # CUAD has 25+ types
        assert len(ContractType) >= 20


class TestDateField:
    """Tests for DateField model."""

    def test_valid_date(self):
        """Valid date should be accepted."""
        date = DateField(year=2024, month=6, day=15)
        assert date.year == 2024
        assert date.month == 6
        assert date.day == 15

    def test_invalid_month_too_high(self):
        """Month > 12 should be rejected."""
        with pytest.raises(ValidationError):
            DateField(year=2024, month=13, day=1)

    def test_invalid_month_zero(self):
        """Month = 0 should be rejected."""
        with pytest.raises(ValidationError):
            DateField(year=2024, month=0, day=1)

    def test_invalid_day_too_high(self):
        """Day > 31 should be rejected."""
        with pytest.raises(ValidationError):
            DateField(year=2024, month=1, day=32)

    def test_invalid_day_zero(self):
        """Day = 0 should be rejected."""
        with pytest.raises(ValidationError):
            DateField(year=2024, month=1, day=0)

    def test_forbid_extra_fields(self):
        """Extra fields should be rejected (additionalProperties: false)."""
        with pytest.raises(ValidationError):
            DateField(year=2024, month=1, day=1, extra_field="bad")


class TestDateComputationResult:
    """Tests for DateComputationResult model."""

    def test_all_dates_present(self):
        """All date fields can be set."""
        result = DateComputationResult(
            agreement_date=DateField(year=2024, month=1, day=1),
            effective_date=DateField(year=2024, month=1, day=15),
            expiration_date=DateField(year=2029, month=1, day=15),
            notice_deadline=DateField(year=2028, month=10, day=15),
            first_renewal_date=DateField(year=2029, month=1, day=15),
        )
        assert result.agreement_date.year == 2024
        assert result.expiration_date.year == 2029

    def test_perpetual_expiration(self):
        """Expiration can be 'perpetual' special value."""
        result = DateComputationResult(
            agreement_date=DateField(year=2024, month=1, day=1),
            effective_date=None,
            expiration_date=SpecialDateValue.PERPETUAL,
            notice_deadline=None,
            first_renewal_date=None,
        )
        assert result.expiration_date == SpecialDateValue.PERPETUAL

    def test_conditional_expiration(self):
        """Expiration can be 'conditional' special value."""
        result = DateComputationResult(
            agreement_date=DateField(year=2024, month=1, day=1),
            effective_date=None,
            expiration_date=SpecialDateValue.CONDITIONAL,
            notice_deadline=None,
            first_renewal_date=None,
        )
        assert result.expiration_date == SpecialDateValue.CONDITIONAL

    def test_null_dates(self):
        """All dates can be None."""
        result = DateComputationResult(
            agreement_date=None,
            effective_date=None,
            expiration_date=None,
            notice_deadline=None,
            first_renewal_date=None,
        )
        assert result.agreement_date is None


class TestExtractedFieldBase:
    """Tests for ExtractedFieldBase model."""

    def test_default_raw_snippet(self):
        """raw_snippet should default to empty string."""
        field = ExtractedFieldBase(reasoning="Test reasoning")
        assert field.raw_snippet == ""
        assert field.reasoning == "Test reasoning"


class TestPartiesExtraction:
    """Tests for PartiesExtraction model."""

    def test_valid_parties(self):
        """Valid parties extraction."""
        parties = PartiesExtraction(
            raw_snippet="Company A and Company B",
            reasoning="Found in the header",
            normalized_value=["Company A", "Company B"],
        )
        assert len(parties.normalized_value) == 2
        assert "Company A" in parties.normalized_value
