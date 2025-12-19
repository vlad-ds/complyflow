"""
Airtable service for contract CRUD operations.
"""

import json
import os
from datetime import datetime
from typing import Any

from pyairtable import Api, Table


# Airtable long text field limit is 100KB, we truncate at 90KB to be safe
AIRTABLE_MAX_TEXT_LENGTH = 90_000


def _truncate_json(data: dict, max_length: int) -> str:
    """
    Convert dict to JSON string, truncating if necessary.

    Args:
        data: Dict to convert
        max_length: Maximum string length

    Returns:
        JSON string, truncated with "...[TRUNCATED]" suffix if too long
    """
    json_str = json.dumps(data, indent=2, default=str)
    if len(json_str) <= max_length:
        return json_str
    # Truncate and add marker
    return json_str[: max_length - 20] + "\n...[TRUNCATED]"


def date_to_iso(d: dict | str | None) -> str | None:
    """Convert date dict {year, month, day} to ISO format string."""
    if d is None:
        return None
    if isinstance(d, str):
        # Already a string, check if it's a special value
        if d in ("perpetual", "conditional"):
            return None
        return d
    if isinstance(d, dict) and "year" in d:
        return f"{d['year']}-{d['month']:02d}-{d['day']:02d}"
    return None


def get_expiration_type(expiration_date: Any) -> str | None:
    """Determine expiration type from the date value."""
    if expiration_date is None:
        return None
    if isinstance(expiration_date, str):
        if expiration_date == "perpetual":
            return "perpetual"
        if expiration_date == "conditional":
            return "conditional"
    if isinstance(expiration_date, dict) and "year" in expiration_date:
        return "absolute"
    return None


def normalize_contract_type(contract_type: str | None) -> str | None:
    """
    Normalize contract type to match Airtable single select options.

    Extraction returns: "Sponsorship Agreement", "Service Agreement", etc.
    Airtable expects: "sponsorship", "services", etc.
    """
    if not contract_type:
        return None

    # Remove " Agreement" suffix and lowercase
    normalized = contract_type.lower().replace(" agreement", "").strip()

    # Handle special cases
    type_mapping = {
        "service": "services",
        "co-branding": "co-branding",
        "non-compete": "non-compete",
        "joint venture": "joint venture",
        "strategic alliance": "strategic alliance",
    }

    return type_mapping.get(normalized, normalized)


class AirtableService:
    """Service for interacting with Airtable Contracts and Corrections tables."""

    def __init__(self):
        api_key = os.environ.get("AIRTABLE_API_KEY")
        base_id = os.environ.get("AIRTABLE_BASE_ID")

        if not api_key:
            raise ValueError("AIRTABLE_API_KEY not set")
        if not base_id:
            raise ValueError("AIRTABLE_BASE_ID not set")

        self.api = Api(api_key)
        self.base_id = base_id
        self.table: Table = self.api.table(base_id, "Contracts")
        self.corrections_table: Table = self.api.table(base_id, "Corrections")
        self.citations_table: Table = self.api.table(base_id, "Citations")

        # Get table ID for URL generation
        self.table_id = self.table.id

    def _to_airtable_fields(self, contract: dict) -> dict:
        """Convert contract dict to Airtable fields format."""
        extraction = contract.get("extraction", {})
        computed_dates = contract.get("computed_dates", {})

        # Handle parties - can be list or dict with normalized_value
        parties = extraction.get("parties")
        if isinstance(parties, dict):
            parties = parties.get("normalized_value", [])
        if isinstance(parties, list):
            parties = json.dumps(parties)
        else:
            parties = str(parties) if parties else ""

        # Handle other extraction fields that might be dicts
        def get_normalized(field_data: Any) -> str | None:
            if field_data is None:
                return None
            if isinstance(field_data, dict):
                return field_data.get("normalized_value")
            return str(field_data)

        # Get expiration date for type determination
        exp_date = computed_dates.get("expiration_date")

        # Normalize contract type for Airtable
        raw_contract_type = get_normalized(extraction.get("contract_type"))
        normalized_type = normalize_contract_type(raw_contract_type)

        fields = {
            "filename": contract.get("filename", ""),
            "parties": parties,
            "contract_type": normalized_type,
            "agreement_date": date_to_iso(computed_dates.get("agreement_date")),
            "effective_date": date_to_iso(computed_dates.get("effective_date")),
            "expiration_date": date_to_iso(exp_date),
            "expiration_type": get_expiration_type(exp_date),
            "notice_deadline": date_to_iso(computed_dates.get("notice_deadline")),
            "first_renewal_date": date_to_iso(computed_dates.get("first_renewal_date")),
            "governing_law": get_normalized(extraction.get("governing_law")),
            "notice_period": get_normalized(extraction.get("notice_period")),
            "renewal_term": get_normalized(extraction.get("renewal_term")),
            "status": "under_review",
            # Exclude 'text' from raw_extraction - it's only needed for embedding, not storage
            "raw_extraction": _truncate_json(
                {k: v for k, v in contract.items() if k != "text"},
                AIRTABLE_MAX_TEXT_LENGTH,
            ),
            "pdf_url": contract.get("pdf_url"),
        }

        # Remove None values - Airtable doesn't like them
        return {k: v for k, v in fields.items() if v is not None}

    def create_contract(self, contract: dict) -> dict:
        """
        Create a new contract record in Airtable.

        Args:
            contract: Dict with 'filename', 'extraction', 'computed_dates'

        Returns:
            Created record with 'id' and 'fields'
        """
        fields = self._to_airtable_fields(contract)
        record = self.table.create(fields)

        # Create citation records for each extracted field
        self._create_citations(record["id"], contract.get("extraction", {}))

        return record

    def _create_citations(self, contract_id: str, extraction: dict) -> list[dict]:
        """
        Create citation records for each extracted field.

        Args:
            contract_id: The Airtable record ID of the contract
            extraction: The extraction dict with field data

        Returns:
            List of created citation records
        """
        # Fields that have citations (raw_snippet + reasoning + normalized_value)
        citation_fields = [
            "parties",
            "contract_type",
            "agreement_date",
            "effective_date",
            "expiration_date",
            "governing_law",
            "notice_period",
            "renewal_term",
        ]

        citations = []
        for field_name in citation_fields:
            field_data = extraction.get(field_name, {})
            if not isinstance(field_data, dict):
                continue

            quote = field_data.get("raw_snippet", "")
            reasoning = field_data.get("reasoning", "")
            normalized_value = field_data.get("normalized_value")

            # Convert ai_value to JSON string for storage
            ai_value_str = json.dumps(normalized_value, default=str) if normalized_value is not None else ""

            # Skip if all are empty
            if not quote and not reasoning and not ai_value_str:
                continue

            citation = self.citations_table.create({
                "field_name": field_name,
                "contract": [contract_id],
                "quote": quote,
                "reasoning": reasoning,
                "ai_value": ai_value_str,
            })
            citations.append(citation)

        return citations

    def get_contract(self, record_id: str) -> dict | None:
        """Get a contract by its Airtable record ID."""
        try:
            return self.table.get(record_id)
        except Exception:
            return None

    def get_citations(self, contract_id: str) -> list[dict]:
        """
        Get all citations for a contract.

        Args:
            contract_id: The Airtable record ID of the contract

        Returns:
            List of citation records with field_name, quote, reasoning, ai_value
        """
        # Get all citations linked to this contract
        all_citations = self.citations_table.all()

        # Filter to those linked to this contract
        contract_citations = []
        for record in all_citations:
            linked_contracts = record.get("fields", {}).get("contract", [])
            if contract_id in linked_contracts:
                contract_citations.append({
                    "id": record["id"],
                    "field_name": record["fields"].get("field_name"),
                    "quote": record["fields"].get("quote", ""),
                    "reasoning": record["fields"].get("reasoning", ""),
                    "ai_value": record["fields"].get("ai_value", ""),
                })

        return contract_citations

    def delete_contract(self, record_id: str) -> bool:
        """Delete a contract by its Airtable record ID."""
        self.table.delete(record_id)
        return True

    def update_contract(self, record_id: str, fields: dict) -> dict:
        """Update a contract record."""
        return self.table.update(record_id, fields)

    def mark_reviewed(self, record_id: str) -> dict:
        """Mark a contract as reviewed."""
        return self.table.update(
            record_id,
            {
                "status": "reviewed",
                "reviewed_at": datetime.now().strftime("%Y-%m-%d"),
            },
        )

    def list_contracts(
        self,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        List contracts with optional status filter.

        Args:
            status: Filter by 'under_review' or 'reviewed'
            limit: Max records to return

        Returns:
            List of contract records
        """
        formula = None
        if status:
            formula = f"{{status}} = '{status}'"

        records = self.table.all(formula=formula, max_records=limit)
        return records

    def get_airtable_url(self, record_id: str) -> str:
        """Get the direct URL to a record in Airtable."""
        return f"https://airtable.com/{self.base_id}/{self.table_id}/{record_id}"

    def find_correction(self, contract_id: str, field_name: str) -> dict | None:
        """Find existing correction for this contract+field."""
        # Filter by field_name in Airtable, then check contract link in Python
        # (Airtable formulas for linked records are unreliable)
        formula = f"{{field_name}} = '{field_name}'"
        records = self.corrections_table.all(formula=formula)

        for record in records:
            # contract field is an array of linked record IDs
            linked_contracts = record.get("fields", {}).get("contract", [])
            if contract_id in linked_contracts:
                return record
        return None

    def log_correction(
        self,
        contract_id: str,
        field_name: str,
        original_value: Any,
        corrected_value: Any,
    ) -> dict:
        """
        Log or update a human correction in the Corrections table.

        - First correction: Creates new record with AI value as original
        - Subsequent edits: Updates corrected_value only (keeps original AI value)

        Args:
            contract_id: Airtable record ID of the contract
            field_name: Name of the field that was corrected
            original_value: The value before this edit (ignored if correction exists)
            corrected_value: The new human-corrected value

        Returns:
            Created or updated correction record
        """
        corrected_str = json.dumps(corrected_value, default=str) if corrected_value is not None else ""

        # Check if correction already exists
        existing = self.find_correction(contract_id, field_name)

        if existing:
            # Update only the corrected_value and timestamp (keep original AI value)
            record = self.corrections_table.update(existing["id"], {
                "corrected_value": corrected_str,
                "corrected_at": datetime.now().isoformat(),
            })
            return record

        # First correction - create new record with AI value as original
        original_str = json.dumps(original_value, default=str) if original_value is not None else ""

        record = self.corrections_table.create({
            "contract": [contract_id],  # Link to contract record
            "field_name": field_name,
            "original_value": original_str,
            "corrected_value": corrected_str,
            "corrected_at": datetime.now().isoformat(),
        })
        return record

    def update_field_with_correction(
        self,
        record_id: str,
        field_name: str,
        original_value: Any,
        new_value: Any,
    ) -> tuple[dict, dict | None]:
        """
        Update a single field and log the correction if value changed.

        Args:
            record_id: Airtable record ID
            field_name: Field to update
            original_value: The original AI-extracted value
            new_value: The new value to set

        Returns:
            Tuple of (updated contract record, correction record or None)
        """
        # Prepare the value for Airtable based on field type
        airtable_value = new_value

        # Handle special field types
        if field_name == "parties" and isinstance(new_value, list):
            airtable_value = json.dumps(new_value)
        elif field_name == "contract_type":
            airtable_value = normalize_contract_type(new_value)
        elif field_name in ("agreement_date", "effective_date", "expiration_date",
                           "notice_deadline", "first_renewal_date"):
            # Convert date dict to ISO string if needed
            airtable_value = date_to_iso(new_value)

        # Update the contract record
        updated = self.table.update(record_id, {field_name: airtable_value})

        # Log correction if value actually changed
        correction = None
        if json.dumps(original_value, default=str) != json.dumps(new_value, default=str):
            correction = self.log_correction(
                contract_id=record_id,
                field_name=field_name,
                original_value=original_value,
                corrected_value=new_value,
            )

        return updated, correction
