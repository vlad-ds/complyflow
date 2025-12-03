"""
Setup script to create the Contracts table in Airtable.

Run once after creating an empty Airtable base:
    uv run python -m api.setup_airtable

Requires .env with:
    AIRTABLE_API_KEY=patXXXXXXXXXXXXXX
    AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX
"""

import os
import sys

from dotenv import load_dotenv
from pyairtable import Api


def get_contract_types() -> list[dict]:
    """Return the 26 contract types from CUAD dataset."""
    return [
        {"name": "affiliate"},
        {"name": "agency"},
        {"name": "collaboration"},
        {"name": "co-branding"},
        {"name": "consulting"},
        {"name": "development"},
        {"name": "distributor"},
        {"name": "endorsement"},
        {"name": "franchise"},
        {"name": "hosting"},
        {"name": "ip"},
        {"name": "joint venture"},
        {"name": "license"},
        {"name": "maintenance"},
        {"name": "manufacturing"},
        {"name": "marketing"},
        {"name": "non-compete"},
        {"name": "outsourcing"},
        {"name": "promotion"},
        {"name": "reseller"},
        {"name": "services"},
        {"name": "sponsorship"},
        {"name": "supply"},
        {"name": "strategic alliance"},
        {"name": "transportation"},
        {"name": "other"},
    ]


def create_contracts_table(api: Api, base_id: str) -> None:
    """Create the Contracts table with all required fields."""
    base = api.base(base_id)

    # Check if table already exists
    schema = base.schema()
    existing_tables = [t.name.lower() for t in schema.tables]
    if "contracts" in existing_tables:
        print("Table 'Contracts' already exists. Skipping creation.")
        return

    fields = [
        {"name": "filename", "type": "singleLineText"},
        {"name": "parties", "type": "multilineText"},
        {
            "name": "contract_type",
            "type": "singleSelect",
            "options": {"choices": get_contract_types()},
        },
        {"name": "agreement_date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
        {"name": "effective_date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
        {"name": "expiration_date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
        {
            "name": "expiration_type",
            "type": "singleSelect",
            "options": {
                "choices": [
                    {"name": "absolute"},
                    {"name": "perpetual"},
                    {"name": "conditional"},
                ]
            },
        },
        {"name": "notice_deadline", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
        {"name": "first_renewal_date", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
        {"name": "governing_law", "type": "singleLineText"},
        {"name": "notice_period", "type": "singleLineText"},
        {"name": "renewal_term", "type": "multilineText"},
        {
            "name": "status",
            "type": "singleSelect",
            "options": {
                "choices": [
                    {"name": "under_review", "color": "yellowBright"},
                    {"name": "reviewed", "color": "greenBright"},
                ]
            },
        },
        {"name": "reviewed_at", "type": "date", "options": {"dateFormat": {"name": "iso"}}},
        {"name": "raw_extraction", "type": "multilineText"},
    ]

    print(f"Creating 'Contracts' table with {len(fields)} fields...")
    table = base.create_table(
        name="Contracts",
        fields=fields,
        description="Contract metadata extracted by ComplyFlow",
    )
    print(f"Created table: {table.name} (ID: {table.id})")
    print("\nFields created:")
    for field in fields:
        print(f"  - {field['name']} ({field['type']})")


def main():
    load_dotenv()

    api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")

    if not api_key:
        print("Error: AIRTABLE_API_KEY not found in .env")
        sys.exit(1)
    if not base_id:
        print("Error: AIRTABLE_BASE_ID not found in .env")
        sys.exit(1)

    print(f"Connecting to Airtable base: {base_id}")
    api = Api(api_key)

    # Verify base access
    try:
        base = api.base(base_id)
        schema = base.schema()
        print(f"Connected to base with {len(schema.tables)} existing table(s)")
    except Exception as e:
        print(f"Error connecting to Airtable: {e}")
        print("\nMake sure your API token has these scopes:")
        print("  - data.records:read")
        print("  - data.records:write")
        print("  - schema.bases:read")
        print("  - schema.bases:write")
        sys.exit(1)

    create_contracts_table(api, base_id)
    print("\nSetup complete!")


if __name__ == "__main__":
    main()
