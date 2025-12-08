"""
Export contracts from Airtable to CSV format.

The CSV is used with Claude's Code Execution Tool for structured data analysis.
"""

import csv
import io
import json
import logging
import os

from pyairtable import Api

logger = logging.getLogger(__name__)


def export_contracts_csv() -> str:
    """
    Export all contracts from Airtable to CSV string.

    Returns:
        CSV string with contract metadata, ready for upload to Files API.

    Raises:
        ValueError: If Airtable credentials not set.
    """
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")

    if not api_key:
        raise ValueError("AIRTABLE_API_KEY not set")
    if not base_id:
        raise ValueError("AIRTABLE_BASE_ID not set")

    api = Api(api_key)
    table = api.table(base_id, "Contracts")

    # Fetch all records
    records = table.all()
    logger.info(f"Fetched {len(records)} contracts from Airtable")

    # Define CSV columns (matching the schema in CLAUDE.md)
    columns = [
        "record_id",
        "filename",
        "parties",
        "contract_type",
        "agreement_date",
        "effective_date",
        "expiration_date",
        "expiration_type",
        "notice_deadline",
        "first_renewal_date",
        "governing_law",
        "notice_period",
        "renewal_term",
        "status",
    ]

    # Write to CSV string
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()

    for record in records:
        fields = record.get("fields", {})
        row = {
            "record_id": record["id"],
            "filename": fields.get("filename", ""),
            "parties": fields.get("parties", ""),  # Already JSON string from Airtable
            "contract_type": fields.get("contract_type", ""),
            "agreement_date": fields.get("agreement_date", ""),
            "effective_date": fields.get("effective_date", ""),
            "expiration_date": fields.get("expiration_date", ""),
            "expiration_type": fields.get("expiration_type", ""),
            "notice_deadline": fields.get("notice_deadline", ""),
            "first_renewal_date": fields.get("first_renewal_date", ""),
            "governing_law": fields.get("governing_law", ""),
            "notice_period": fields.get("notice_period", ""),
            "renewal_term": fields.get("renewal_term", ""),
            "status": fields.get("status", ""),
        }
        writer.writerow(row)

    csv_content = output.getvalue()
    logger.info(f"Generated CSV with {len(records)} rows, {len(csv_content)} bytes")

    return csv_content


def get_contract_count() -> int:
    """
    Get the count of contracts in Airtable (for diagnostics).

    Returns:
        Number of contracts.
    """
    api_key = os.environ.get("AIRTABLE_API_KEY")
    base_id = os.environ.get("AIRTABLE_BASE_ID")

    if not api_key or not base_id:
        return 0

    api = Api(api_key)
    table = api.table(base_id, "Contracts")
    records = table.all()
    return len(records)
