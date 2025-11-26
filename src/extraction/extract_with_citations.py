"""Contract metadata extraction using Anthropic's citations feature.

Extracts structured metadata from contract PDFs with citations pointing
to the source text in the document.
"""

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from anthropic import Anthropic
from anthropic.types import Message

from extraction.schema import ContractType


@dataclass
class CitedValue:
    """A value extracted from a document with its citation."""

    value: str | list[str] | None
    citations: list[dict]


@dataclass
class ExtractedContractWithCitations:
    """Contract metadata with citations for each field."""

    parties: CitedValue
    contract_type: CitedValue
    notice_period: CitedValue
    expiration_date: CitedValue
    renewal_term: CitedValue
    raw_response: Message


EXTRACTION_PROMPT = """Analyze this contract and extract the following information. For each field, explain what you found in the document by quoting the relevant passages, then provide the extracted value.

Extract these fields:
1. **parties**: List all named parties to the contract (company names, individuals, etc.)
2. **contract_type**: Classify the contract type. Must be one of: {contract_types}
3. **notice_period**: The notice period required to terminate or not renew the contract (e.g., "90 days prior written notice"). Return null if not specified.
4. **expiration_date**: When the contract expires or terminates. Return null if not specified.
5. **renewal_term**: Auto-renewal terms, if any (e.g., "successive one-year periods"). Return null if not specified.

For each field, structure your response like this:

## Parties
The document states [quote the relevant text identifying the parties]. Based on this, the parties are: [list parties]

## Contract Type
The document is titled [quote title] and describes [quote relevant sections]. This is a: [type]

## Notice Period
The document states [quote relevant text about notice requirements]. The notice period is: [value or null]

## Expiration Date
The document states [quote relevant text about expiration/termination]. The expiration date is: [value or null]

## Renewal Term
The document states [quote relevant text about renewal]. The renewal term is: [value or null]

After your analysis, provide a JSON summary:
```json
{{
  "parties": ["Party 1", "Party 2"],
  "contract_type": "Type",
  "notice_period": "value or null",
  "expiration_date": "value or null",
  "renewal_term": "value or null"
}}
```

Important: Quote directly from the document to support each extraction.
"""


def _load_pdf_as_base64(pdf_path: Path) -> str:
    """Load a PDF file and return its base64 encoding."""
    with open(pdf_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def _get_contract_types_str() -> str:
    """Get a formatted string of all valid contract types."""
    return ", ".join(f'"{ct.value}"' for ct in ContractType)


def _parse_citations_by_section(response: Message) -> dict[str, list[dict]]:
    """Parse citations from the response, grouped by section.

    The response has markdown sections (## Parties, ## Contract Type, etc.)
    with cited text blocks followed by analysis.

    Returns a dict mapping section names to their citations.
    """
    section_citations: dict[str, list[dict]] = {
        "parties": [],
        "contract_type": [],
        "notice_period": [],
        "expiration_date": [],
        "renewal_term": [],
    }

    current_section = None

    for block in response.content:
        if block.type != "text":
            continue

        text = block.text

        # Check if this block starts a new section
        if "## Parties" in text:
            current_section = "parties"
        elif "## Contract Type" in text:
            current_section = "contract_type"
        elif "## Notice Period" in text:
            current_section = "notice_period"
        elif "## Expiration Date" in text:
            current_section = "expiration_date"
        elif "## Renewal Term" in text:
            current_section = "renewal_term"

        # If this block has citations, add them to the current section
        if current_section and hasattr(block, "citations") and block.citations:
            for citation in block.citations:
                citation_data = {
                    "type": citation.type,
                    "cited_text": citation.cited_text,
                }
                if citation.type == "page_location":
                    citation_data["document_index"] = citation.document_index
                    citation_data["start_page"] = citation.start_page_number
                    citation_data["end_page"] = citation.end_page_number
                elif citation.type == "char_location":
                    citation_data["document_index"] = citation.document_index
                    citation_data["start_char_index"] = citation.start_char_index
                    citation_data["end_char_index"] = citation.end_char_index

                section_citations[current_section].append(citation_data)

    return section_citations


def _get_full_response_text(response: Message) -> str:
    """Concatenate all text blocks from the response."""
    return "".join(
        block.text for block in response.content if block.type == "text"
    )


def _extract_json_from_response(response_text: str) -> dict:
    """Extract JSON from response text, handling markdown code blocks."""
    # Try to find JSON in code block
    if "```json" in response_text:
        start = response_text.find("```json") + 7
        end = response_text.find("```", start)
        json_str = response_text[start:end].strip()
    elif "```" in response_text:
        start = response_text.find("```") + 3
        end = response_text.find("```", start)
        json_str = response_text[start:end].strip()
    else:
        # Try to parse the whole response as JSON
        json_str = response_text.strip()

    return json.loads(json_str)


def extract_contract_metadata(
    client: Anthropic,
    pdf_path: Path | str,
    model: str = "claude-sonnet-4-5-20250929",
) -> ExtractedContractWithCitations:
    """Extract contract metadata with citations from a PDF.

    Args:
        client: Anthropic client instance.
        pdf_path: Path to the contract PDF file.
        model: Claude model to use for extraction.

    Returns:
        ExtractedContractWithCitations containing extracted values and citations.
    """
    pdf_path = Path(pdf_path)
    pdf_base64 = _load_pdf_as_base64(pdf_path)

    prompt = EXTRACTION_PROMPT.format(contract_types=_get_contract_types_str())

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64,
                        },
                        "title": pdf_path.name,
                        "citations": {"enabled": True},
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    # Get the full text and parse JSON
    response_text = _get_full_response_text(response)
    extracted_data = _extract_json_from_response(response_text)

    # Parse citations by section
    section_citations = _parse_citations_by_section(response)

    return ExtractedContractWithCitations(
        parties=CitedValue(
            value=extracted_data.get("parties", []),
            citations=section_citations["parties"],
        ),
        contract_type=CitedValue(
            value=extracted_data.get("contract_type"),
            citations=section_citations["contract_type"],
        ),
        notice_period=CitedValue(
            value=extracted_data.get("notice_period"),
            citations=section_citations["notice_period"],
        ),
        expiration_date=CitedValue(
            value=extracted_data.get("expiration_date"),
            citations=section_citations["expiration_date"],
        ),
        renewal_term=CitedValue(
            value=extracted_data.get("renewal_term"),
            citations=section_citations["renewal_term"],
        ),
        raw_response=response,
    )


def format_extraction_result(result: ExtractedContractWithCitations) -> str:
    """Format extraction results for display."""
    lines = ["=" * 60, "EXTRACTED CONTRACT METADATA WITH CITATIONS", "=" * 60, ""]

    def format_field(name: str, cited_value: CitedValue) -> list[str]:
        field_lines = [f"### {name.upper()}"]
        if cited_value.value is None:
            field_lines.append("  Value: null")
        elif isinstance(cited_value.value, list):
            field_lines.append("  Value:")
            for v in cited_value.value:
                field_lines.append(f"    - {v}")
        else:
            field_lines.append(f"  Value: {cited_value.value}")

        if cited_value.citations:
            field_lines.append("  Citations:")
            for i, cit in enumerate(cited_value.citations, 1):
                cited_text = cit.get("cited_text", "")[:150]
                if len(cit.get("cited_text", "")) > 150:
                    cited_text += "..."
                # Clean up whitespace in cited text
                cited_text = " ".join(cited_text.split())
                if cit.get("type") == "page_location":
                    start_page = cit.get("start_page", "?")
                    end_page = cit.get("end_page", "?")
                    if start_page == end_page:
                        page_info = f"p.{start_page}"
                    else:
                        page_info = f"pp.{start_page}-{end_page}"
                    field_lines.append(f"    [{i}] ({page_info}) \"{cited_text}\"")
                else:
                    field_lines.append(f"    [{i}] \"{cited_text}\"")
        else:
            field_lines.append("  Citations: (none found)")

        field_lines.append("")
        return field_lines

    lines.extend(format_field("parties", result.parties))
    lines.extend(format_field("contract_type", result.contract_type))
    lines.extend(format_field("notice_period", result.notice_period))
    lines.extend(format_field("expiration_date", result.expiration_date))
    lines.extend(format_field("renewal_term", result.renewal_term))

    # Usage stats
    lines.extend(
        [
            "-" * 60,
            "USAGE STATISTICS",
            "-" * 60,
            f"Input tokens: {result.raw_response.usage.input_tokens}",
            f"Output tokens: {result.raw_response.usage.output_tokens}",
            f"Model: {result.raw_response.model}",
        ]
    )

    return "\n".join(lines)
