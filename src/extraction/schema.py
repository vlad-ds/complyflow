"""Schema for LLM contract metadata extraction."""

from enum import Enum

from pydantic import BaseModel, Field


class ContractType(str, Enum):
    """Contract types from CUAD dataset."""

    AFFILIATE = "Affiliate Agreement"
    AGENCY = "Agency Agreement"
    CO_BRANDING = "Co-Branding Agreement"
    COLLABORATION = "Collaboration Agreement"
    CONSULTING = "Consulting Agreement"
    DEVELOPMENT = "Development Agreement"
    DISTRIBUTOR = "Distributor Agreement"
    ENDORSEMENT = "Endorsement Agreement"
    FRANCHISE = "Franchise Agreement"
    HOSTING = "Hosting Agreement"
    IP = "IP Agreement"
    JOINT_VENTURE = "Joint Venture Agreement"
    LICENSE = "License Agreement"
    MAINTENANCE = "Maintenance Agreement"
    MANUFACTURING = "Manufacturing Agreement"
    MARKETING = "Marketing Agreement"
    NON_COMPETE = "Non-Compete Agreement"
    OUTSOURCING = "Outsourcing Agreement"
    PROMOTION = "Promotion Agreement"
    RESELLER = "Reseller Agreement"
    SERVICE = "Service Agreement"
    SPONSORSHIP = "Sponsorship Agreement"
    STRATEGIC_ALLIANCE = "Strategic Alliance Agreement"
    SUPPLY = "Supply Agreement"
    TRANSPORTATION = "Transportation Agreement"


# --- Extraction response schemas (with raw_snippet + reasoning) ---
# NOTE: We avoid nullable types (str | None) to reduce anyOf branches in JSON schema,
# which Anthropic's structured output limits to 8. Use empty string "" for missing values.


class ExtractedFieldBase(BaseModel):
    """Base for extracted fields with raw snippet and reasoning."""

    raw_snippet: str = Field(
        default="",
        description="Exact verbatim text copied from the document. Empty string if not found."
    )
    reasoning: str = Field(
        description="Brief explanation of how the value was identified and interpreted."
    )


class PartiesExtraction(ExtractedFieldBase):
    """Parties field extraction."""

    normalized_value: list[str] = Field(
        description="List of party names (company/person names only, not roles like 'Licensor')"
    )


class ContractTypeExtraction(ExtractedFieldBase):
    """Contract type field extraction."""

    normalized_value: str = Field(
        description="Contract type from predefined categories"
    )


class StringFieldExtraction(ExtractedFieldBase):
    """Generic string field extraction (notice_period, expiration_date, renewal_term)."""

    normalized_value: str = Field(
        default="",
        description="Standardized/normalized value, or empty string if not found"
    )


class ExtractionResponse(BaseModel):
    """Full extraction response from LLM."""

    parties: PartiesExtraction
    contract_type: ContractTypeExtraction
    agreement_date: StringFieldExtraction
    effective_date: StringFieldExtraction
    expiration_date: StringFieldExtraction
    governing_law: StringFieldExtraction
    notice_period: StringFieldExtraction
    renewal_term: StringFieldExtraction


# --- Date Computation schemas ---


class SpecialDateValue(str, Enum):
    """Special values for dates that cannot be computed to a specific date."""

    PERPETUAL = "perpetual"  # Contract has no expiration (runs indefinitely)
    CONDITIONAL = "conditional"  # Expiration depends on an event, not a fixed date


class DateField(BaseModel):
    """A specific calendar date."""

    model_config = {"extra": "forbid"}  # additionalProperties: false

    year: int = Field(description="4-digit year (e.g., 2024)")
    month: int = Field(ge=1, le=12, description="Month (1-12)")
    day: int = Field(ge=1, le=31, description="Day of month (1-31)")


class DateComputationResult(BaseModel):
    """Result of date computation from extracted contract fields.

    Each date field can be:
    - DateField: A specific computed date
    - SpecialDateValue: "perpetual" or "conditional"
    - None: Date not available or cannot be computed
    """

    model_config = {"extra": "forbid"}  # additionalProperties: false

    agreement_date: DateField | None = Field(
        description="When the contract was signed"
    )
    effective_date: DateField | None = Field(
        description="When the contract takes effect"
    )
    expiration_date: DateField | SpecialDateValue | None = Field(
        description="When the contract expires. Can be 'perpetual' or 'conditional' for special cases"
    )
    notice_deadline: DateField | None = Field(
        description="Deadline to give notice to prevent auto-renewal (expiration - notice_period)"
    )
    first_renewal_date: DateField | None = Field(
        description="When first renewal period starts (equals expiration if auto-renewal exists)"
    )
