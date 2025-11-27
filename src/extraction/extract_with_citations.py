"""Contract metadata extraction with structured JSON output.

Extracts structured metadata from contract text with:
- Raw snippets (verbatim quotes from the document)
- Claude's reasoning for each extraction
- Normalized values
"""

from pathlib import Path

import anthropic
from langfuse import get_client, observe

from extraction.schema import ContractType, ExtractionResponse
from prompts import load_prompt


def _load_text_file(text_path: Path) -> str:
    """Load a text file and return its contents."""
    with open(text_path, "r") as f:
        return f.read()


def _get_contract_types_str() -> str:
    """Get a formatted string of all valid contract types."""
    return ", ".join(f'"{ct.value}"' for ct in ContractType)


def _get_json_schema() -> dict:
    """Get JSON schema from Pydantic model for Anthropic's structured output.

    Anthropic requires additionalProperties: false on all objects.
    """
    schema = ExtractionResponse.model_json_schema()

    # Recursively add additionalProperties: false to all objects
    def add_additional_properties(obj: dict) -> dict:
        if isinstance(obj, dict):
            if obj.get("type") == "object":
                obj["additionalProperties"] = False
            for key, value in obj.items():
                if isinstance(value, dict):
                    add_additional_properties(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            add_additional_properties(item)
        return obj

    # Inline $defs references and add additionalProperties
    if "$defs" in schema:
        defs = schema.pop("$defs")
        # Add additionalProperties to all defs
        for def_schema in defs.values():
            add_additional_properties(def_schema)

        # Replace $ref with actual definitions
        def resolve_refs(obj: dict) -> dict:
            if isinstance(obj, dict):
                if "$ref" in obj:
                    ref_name = obj["$ref"].split("/")[-1]
                    return defs[ref_name].copy()
                return {k: resolve_refs(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [resolve_refs(item) for item in obj]
            return obj

        schema = resolve_refs(schema)

    add_additional_properties(schema)
    return schema


@observe(name="contract-extraction")
def extract_contract_metadata(
    client: anthropic.Anthropic,
    text_path: Path | str,
    model: str = "claude-sonnet-4-5-20250929",
) -> ExtractionResponse:
    """Extract contract metadata from a text file.

    Uses structured JSON output for reliable parsing. All API calls are traced
    in Langfuse via OpenTelemetry instrumentation.

    Args:
        client: Anthropic client instance.
        text_path: Path to the contract text file.
        model: Claude model to use for extraction.

    Returns:
        ExtractionResponse with raw snippets, reasoning, and normalized values.
    """
    text_path = Path(text_path)
    prompt_template = load_prompt("extraction_v1")
    prompt = prompt_template.format(contract_types=_get_contract_types_str())
    text_content = _load_text_file(text_path)

    # Update current trace with document info
    langfuse = get_client()
    langfuse.update_current_trace(
        metadata={"document": text_path.name, "model": model}
    )

    # API call with structured JSON output (beta feature)
    response = client.beta.messages.create(
        model=model,
        max_tokens=4096,
        betas=["structured-outputs-2025-11-13"],
        messages=[
            {
                "role": "user",
                "content": f"<contract>\n{text_content}\n</contract>\n\n{prompt}",
            }
        ],
        output_format={
            "type": "json_schema",
            "schema": _get_json_schema(),
        },
    )

    # Parse and validate with Pydantic
    result = ExtractionResponse.model_validate_json(response.content[0].text)

    # Attach raw response for token usage
    result._raw_response = response  # type: ignore

    return result


def format_extraction_result(result: ExtractionResponse) -> str:
    """Format extraction results for display."""
    lines = ["=" * 70, "EXTRACTED CONTRACT METADATA", "=" * 70, ""]

    def format_field(name: str, field) -> list[str]:
        field_lines = ["-" * 70, f"## {name.upper()}", "-" * 70]
        field_lines.append(f"Raw snippet: {field.raw_snippet}")
        field_lines.append(f"Reasoning: {field.reasoning}")
        field_lines.append(f"Normalized: {field.normalized_value}")
        field_lines.append("")
        return field_lines

    lines.extend(format_field("parties", result.parties))
    lines.extend(format_field("contract_type", result.contract_type))
    lines.extend(format_field("notice_period", result.notice_period))
    lines.extend(format_field("expiration_date", result.expiration_date))
    lines.extend(format_field("renewal_term", result.renewal_term))

    # Usage stats from raw response if available
    if hasattr(result, "_raw_response"):
        raw = result._raw_response
        lines.extend([
            "=" * 70,
            "USAGE",
            "=" * 70,
            f"Model: {raw.model}",
            f"Input tokens: {raw.usage.input_tokens}",
            f"Output tokens: {raw.usage.output_tokens}",
        ])

    return "\n".join(lines)
