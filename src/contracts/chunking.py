"""
Contract chunking for vector search.

Splits contracts into chunks with metadata headers for semantic searchability.
"""

import json
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from contracts.config import ContractEmbedConfig


def format_contract_header(
    contract_id: str,
    filename: str,
    contract_type: str | None = None,
    parties: list[str] | None = None,
    governing_law: str | None = None,
) -> str:
    """
    Format contract metadata as a searchable header to prepend to chunk text.

    This enables semantic search to find contracts by their identifiers
    (contract ID, filename, type, parties) - not just by content similarity.

    Args:
        contract_id: Airtable record ID
        filename: Original PDF filename
        contract_type: Type of contract (services, license, etc.)
        parties: List of party names
        governing_law: Jurisdiction

    Returns:
        Formatted header string like:
        "[Contract ID: rec123xyz | Type: services]
        Parties: Company A Inc., Company B LLC
        Filename: master_services_agreement.pdf
        ---"
    """
    parts = []

    # Primary identifier line with bracketed metadata
    id_parts = [f"Contract ID: {contract_id}"]
    if contract_type:
        id_parts.append(f"Type: {contract_type}")
    parts.append(f"[{' | '.join(id_parts)}]")

    # Parties on separate line
    if parties:
        parties_str = ", ".join(parties) if isinstance(parties, list) else str(parties)
        parts.append(f"Parties: {parties_str}")

    # Filename
    parts.append(f"Filename: {filename}")

    # Governing law if available
    if governing_law:
        parts.append(f"Governing Law: {governing_law}")

    # Separator
    parts.append("---")

    return "\n".join(parts) + "\n"


def create_splitter(config: ContractEmbedConfig) -> RecursiveCharacterTextSplitter:
    """Create a text splitter with the given configuration."""
    return RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_contract(
    text: str,
    contract_id: str,
    filename: str,
    extraction: dict[str, Any],
    config: ContractEmbedConfig | None = None,
) -> list[dict]:
    """
    Split a contract into chunks with metadata payload.

    Each chunk's text is prepended with a metadata header containing the contract
    identifier, type, and parties. This enables semantic search to find contracts
    by their identifiers.

    Args:
        text: Full contract text
        contract_id: Airtable record ID
        filename: Original PDF filename
        extraction: Extraction results dict with parties, contract_type, etc.
        config: Embedding configuration (uses defaults if not provided)

    Returns:
        List of chunk dicts with:
        - text: The chunk text (with metadata header prepended)
        - chunk_index: Position in document
        - contract_id, filename, contract_type, parties, governing_law
    """
    config = config or ContractEmbedConfig()
    splitter = create_splitter(config)
    splits = splitter.split_text(text)

    # Extract metadata from extraction results
    # Handle nested structure: extraction["parties"]["normalized_value"]
    parties_data = extraction.get("parties", {})
    if isinstance(parties_data, dict):
        parties = parties_data.get("normalized_value", [])
    else:
        parties = parties_data if isinstance(parties_data, list) else []

    contract_type_data = extraction.get("contract_type", {})
    if isinstance(contract_type_data, dict):
        contract_type = contract_type_data.get("normalized_value", "")
    else:
        contract_type = contract_type_data if isinstance(contract_type_data, str) else ""

    governing_law_data = extraction.get("governing_law", {})
    if isinstance(governing_law_data, dict):
        governing_law = governing_law_data.get("normalized_value", "")
    else:
        governing_law = governing_law_data if isinstance(governing_law_data, str) else ""

    # Create metadata header once (same for all chunks)
    metadata_header = format_contract_header(
        contract_id=contract_id,
        filename=filename,
        contract_type=contract_type,
        parties=parties,
        governing_law=governing_law,
    )

    chunks = []
    for i, chunk_text in enumerate(splits):
        chunk = {
            "contract_id": contract_id,
            "filename": filename,
            "contract_type": contract_type,
            "parties": json.dumps(parties) if parties else "[]",
            "governing_law": governing_law,
            "chunk_index": i,
            # Prepend metadata header so semantic search can find by ID/type/parties
            "text": metadata_header + chunk_text,
        }
        chunks.append(chunk)

    return chunks
