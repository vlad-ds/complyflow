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


class ExtractedContractMetadata(BaseModel):
    """Metadata extracted from contract PDF by LLM.

    All fields map directly to CUAD ground truth for evaluation.
    """

    parties: list[str] = Field(
        description="All named parties to the contract"
    )
    contract_type: ContractType = Field(
        description="Type of contract from predefined categories"
    )
    notice_period: str | None = Field(
        default=None,
        description="Notice period required to terminate or not renew (e.g., '90 days prior written notice')",
    )
    expiration_date: str | None = Field(
        default=None,
        description="When the contract expires or terminates, as stated in the document",
    )
    renewal_term: str | None = Field(
        default=None,
        description="Auto-renewal terms, if any (e.g., 'successive one-year periods')",
    )
