"""Provider-agnostic contract metadata extraction.

This module provides a unified interface for extracting contract metadata
using any LLM provider (Anthropic, OpenAI, Gemini).
"""

from pathlib import Path

from langfuse import get_client, observe

from extraction.schema import ContractType, ExtractionResponse
from llm.base import BaseLLMProvider, LLMResponse
from prompts import load_prompt


def _load_text_file(text_path: Path) -> str:
    """Load a text file and return its contents."""
    with open(text_path, "r") as f:
        return f.read()


def _get_contract_types_str() -> str:
    """Get a formatted string of all valid contract types."""
    return ", ".join(f'"{ct.value}"' for ct in ContractType)


def _get_json_schema() -> dict:
    """Get JSON schema from Pydantic model for structured output.

    Ensures additionalProperties: false on all objects as required
    by most providers for strict schema adherence.
    """
    schema = ExtractionResponse.model_json_schema()

    # Recursively add additionalProperties: false and required fields to all objects
    def fix_object_schema(obj: dict) -> dict:
        if isinstance(obj, dict):
            if obj.get("type") == "object":
                obj["additionalProperties"] = False
                # OpenAI requires 'required' to list ALL properties (even those with defaults)
                if "properties" in obj:
                    obj["required"] = list(obj["properties"].keys())
            for key, value in obj.items():
                if isinstance(value, dict):
                    fix_object_schema(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            fix_object_schema(item)
        return obj

    # Inline $defs references and fix schema
    if "$defs" in schema:
        defs = schema.pop("$defs")
        # Fix all defs
        for def_schema in defs.values():
            fix_object_schema(def_schema)

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

    fix_object_schema(schema)
    return schema


@observe(name="contract-extraction")
def extract_contract_metadata(
    provider: BaseLLMProvider,
    text_path: Path | str,
    model: str | None = None,
    eval_id: str | None = None,
) -> ExtractionResponse:
    """Extract contract metadata from a text file using any LLM provider.

    Args:
        provider: LLM provider instance (Anthropic, OpenAI, or Gemini).
        text_path: Path to the contract text file.
        model: Optional model override (uses provider's default if None).
        eval_id: Optional evaluation run ID for Langfuse tagging.

    Returns:
        ExtractionResponse with raw snippets, reasoning, and normalized values.
    """
    text_path = Path(text_path)
    prompt_template = load_prompt("extraction_v1")
    prompt = prompt_template.format(contract_types=_get_contract_types_str())
    text_content = _load_text_file(text_path)

    # Build tags list
    tags = [f"provider:{provider.provider_name}", f"model:{model or provider.default_model}"]
    if eval_id:
        tags.append(eval_id)

    # Update current trace with document and provider info
    langfuse = get_client()
    langfuse.update_current_trace(
        name=f"extraction-{provider.provider_name}",
        metadata={
            "document": text_path.name,
            "provider": provider.provider_name,
            "model": model or provider.default_model,
            "eval_id": eval_id,
        },
        session_id=provider.get_langfuse_session_name(),
        tags=tags,
    )

    # Call provider's extraction method
    llm_response: LLMResponse = provider.extract_json(
        prompt=prompt,
        document=text_content,
        json_schema=_get_json_schema(),
        model=model,
    )

    # Parse and validate with Pydantic
    result = ExtractionResponse.model_validate_json(llm_response.content)

    # Attach response metadata for later use
    result._llm_response = llm_response  # type: ignore

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

    # Usage stats from LLM response if available
    if hasattr(result, "_llm_response"):
        resp = result._llm_response
        lines.extend([
            "=" * 70,
            "USAGE",
            "=" * 70,
            f"Model: {resp.model}",
            f"Input tokens: {resp.input_tokens}",
            f"Output tokens: {resp.output_tokens}",
        ])

    return "\n".join(lines)
