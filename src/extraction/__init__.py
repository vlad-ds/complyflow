"""Contract metadata extraction module."""

from extraction.extract_with_citations import (
    extract_contract_metadata,
    format_extraction_result,
)
from extraction.schema import (
    ContractType,
    ContractTypeExtraction,
    ExtractionResponse,
    PartiesExtraction,
    StringFieldExtraction,
)

__all__ = [
    "ContractType",
    "ContractTypeExtraction",
    "ExtractionResponse",
    "PartiesExtraction",
    "StringFieldExtraction",
    "extract_contract_metadata",
    "format_extraction_result",
]
