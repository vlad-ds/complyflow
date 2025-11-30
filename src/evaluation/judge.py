"""LLM-as-judge evaluation for contract extraction.

Uses Gemini Flash to judge whether model extractions match ground truth.
Handles special cases (empty values, exact match fields) programmatically.
"""

import csv
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from langfuse import Langfuse
from pydantic import BaseModel, Field

load_dotenv()

# Paths to prompt templates
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
JUDGE_PROMPT_PATH = PROMPTS_DIR / "judge_v1.md"
FIELD_GUIDANCE_PATH = PROMPTS_DIR / "judge_field_guidance.md"

# Fields that use exact string matching (no LLM needed)
EXACT_MATCH_FIELDS = {"contract_type"}

# All fields we evaluate
EVAL_FIELDS = [
    "parties",
    "contract_type",
    "agreement_date",
    "effective_date",
    "expiration_date",
    "governing_law",
    "notice_period",
    "renewal_term",
]

# Mapping from our field names to CUAD ground truth field names
FIELD_TO_GT = {
    "parties": "Parties",
    "contract_type": "contract_type",
    "agreement_date": "Agreement Date",
    "effective_date": "Effective Date",
    "expiration_date": "Expiration Date",
    "governing_law": "Governing Law",
    "notice_period": "Notice Period To Terminate Renewal",
    "renewal_term": "Renewal Term",
}


class Judgment(str, Enum):
    """Judgment values for LLM judge."""
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"


class JudgeResponse(BaseModel):
    """Structured response from LLM judge."""
    reasoning: str = Field(description="Brief explanation of why this judgment was made")
    judgment: Judgment = Field(description="Whether the model output matches ground truth")


@dataclass
class JudgmentResult:
    """Result of judging a single field extraction."""

    field: str
    judgment: str  # "MATCH", "NO_MATCH", or "ERROR"
    reasoning: str
    method: str  # "empty_check", "exact_match", or "llm_judge"
    ground_truth: str
    model_output: str


def _load_prompt_template() -> str:
    """Load the judge prompt template."""
    with open(JUDGE_PROMPT_PATH) as f:
        return f.read()


def _load_field_guidance() -> dict[str, str]:
    """Load field-specific guidance from markdown file.

    Returns:
        Dict mapping field name to guidance text.
    """
    with open(FIELD_GUIDANCE_PATH) as f:
        content = f.read()

    guidance = {}
    current_field = None
    current_lines = []

    for line in content.split("\n"):
        if line.startswith("## ") and not line.startswith("## Field"):
            # Save previous field
            if current_field:
                guidance[current_field] = "\n".join(current_lines).strip()
            # Start new field
            current_field = line[3:].strip()
            current_lines = []
        elif current_field and not line.startswith("# "):
            current_lines.append(line)

    # Save last field
    if current_field:
        guidance[current_field] = "\n".join(current_lines).strip()

    return guidance


# Load templates once at module level
_PROMPT_TEMPLATE = _load_prompt_template()
_FIELD_GUIDANCE = _load_field_guidance()


def _is_empty(value: str) -> bool:
    """Check if a value is empty or whitespace-only."""
    return not value or value.strip() == ""


def _get_ground_truth_value(gt: dict, field: str) -> str:
    """Extract ground truth value for a field."""
    gt_field = FIELD_TO_GT.get(field, field)
    value = gt.get(gt_field, [])

    if isinstance(value, list):
        return "\n".join(value) if value else ""
    return str(value) if value else ""


def _get_model_output_value(model_output: dict, field: str) -> str:
    """Extract model's normalized_value for a field."""
    extraction = model_output.get("extraction", {})
    field_data = extraction.get(field, {})
    value = field_data.get("normalized_value", "")

    if isinstance(value, list):
        return "\n".join(value) if value else ""
    return str(value) if value else ""


def judge_field(
    field: str,
    ground_truth: str,
    model_output: str,
    client: genai.Client | None = None,
) -> JudgmentResult:
    """Judge whether a model's extraction matches ground truth for a field.

    Args:
        field: Field name (e.g., "parties", "contract_type").
        ground_truth: Ground truth value (may be multi-line for lists).
        model_output: Model's extracted value.
        client: Optional Gemini client (created if not provided).

    Returns:
        JudgmentResult with judgment, reasoning, and method used.
    """
    # Handle empty values programmatically (Flash gets this wrong)
    gt_empty = _is_empty(ground_truth)
    mo_empty = _is_empty(model_output)

    if gt_empty and mo_empty:
        return JudgmentResult(
            field=field,
            judgment="MATCH",
            reasoning="Both ground truth and model output are empty",
            method="empty_check",
            ground_truth=ground_truth,
            model_output=model_output,
        )

    if gt_empty != mo_empty:
        return JudgmentResult(
            field=field,
            judgment="NO_MATCH",
            reasoning=f"One is empty, other is not (GT empty={gt_empty}, Model empty={mo_empty})",
            method="empty_check",
            ground_truth=ground_truth,
            model_output=model_output,
        )

    # Handle exact match fields (contract_type)
    if field in EXACT_MATCH_FIELDS:
        is_match = ground_truth.lower().strip() == model_output.lower().strip()
        return JudgmentResult(
            field=field,
            judgment="MATCH" if is_match else "NO_MATCH",
            reasoning=f"Exact match: '{ground_truth}' vs '{model_output}'",
            method="exact_match",
            ground_truth=ground_truth,
            model_output=model_output,
        )

    # Use LLM judge for semantic comparison with structured output
    if client is None:
        client = genai.Client()

    guidance = _FIELD_GUIDANCE.get(field, "Compare the semantic meaning of both values.")

    prompt = _PROMPT_TEMPLATE.format(
        field=field,
        field_guidance=guidance,
        ground_truth=ground_truth,
        model_output=model_output,
    )

    # Build JSON schema from Pydantic model
    judge_schema = JudgeResponse.model_json_schema()

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": judge_schema,
            },
        )

        # Parse structured response
        result = JudgeResponse.model_validate_json(response.text)

        return JudgmentResult(
            field=field,
            judgment=result.judgment.value,
            reasoning=result.reasoning,
            method="llm_judge",
            ground_truth=ground_truth,
            model_output=model_output,
        )

    except Exception as e:
        return JudgmentResult(
            field=field,
            judgment="ERROR",
            reasoning=f"Failed to parse LLM response: {e}",
            method="llm_judge",
            ground_truth=ground_truth,
            model_output=model_output,
        )


def judge_extraction(
    ground_truth: dict,
    model_output: dict,
    fields: list[str] | None = None,
    client: genai.Client | None = None,
) -> list[JudgmentResult]:
    """Judge all fields of a model's extraction against ground truth.

    Args:
        ground_truth: Ground truth dict from CUAD metadata.
        model_output: Model's extraction output dict.
        fields: Fields to evaluate (defaults to EVAL_FIELDS).
        client: Optional Gemini client (reused across calls).

    Returns:
        List of JudgmentResult for each field.
    """
    fields = fields or EVAL_FIELDS
    if client is None:
        client = genai.Client()

    results = []
    for field in fields:
        gt_value = _get_ground_truth_value(ground_truth, field)
        mo_value = _get_model_output_value(model_output, field)
        result = judge_field(field, gt_value, mo_value, client)
        results.append(result)

    return results


def _calculate_metrics(stats: dict) -> dict:
    """Calculate accuracy from match/no_match counts."""
    total = stats.get("total", 0)
    match = stats.get("match", 0)

    if total == 0:
        return stats

    stats["accuracy"] = match / total
    return stats


def judge_eval_pairs(
    eval_pairs: list[dict],
    models: list[str] | None = None,
    fields: list[str] | None = None,
    eval_id: str | None = None,
) -> dict:
    """Judge all eval pairs and return aggregated results.

    Args:
        eval_pairs: List of eval pair dicts from eval_pairs JSON.
        models: Models to evaluate (defaults to all in eval_pairs).
        fields: Fields to evaluate (defaults to EVAL_FIELDS).
        eval_id: Unique ID for this evaluation run (for Langfuse tagging).

    Returns:
        Dict with per-model, per-field, and per-contract results, plus run metadata.
    """
    fields = fields or EVAL_FIELDS
    client = genai.Client()

    # Generate eval_id if not provided
    if eval_id is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        eval_id = f"judge_{timestamp}_{short_uuid}"

    # Track timing
    start_time = time.time()

    # Collect all judgments
    all_results = []
    llm_call_count = 0

    for pair in eval_pairs:
        contract_file = pair["contract_file"]
        ground_truth = pair["ground_truth"]
        model_outputs = pair["model_outputs"]

        # Filter models if specified
        eval_models = models or list(model_outputs.keys())

        for model in eval_models:
            if model not in model_outputs:
                continue

            model_output = model_outputs[model]
            judgments = judge_extraction(ground_truth, model_output, fields, client)

            for j in judgments:
                all_results.append({
                    "contract": contract_file,
                    "model": model,
                    "field": j.field,
                    "judgment": j.judgment,
                    "reasoning": j.reasoning,
                    "method": j.method,
                    "ground_truth": j.ground_truth,
                    "model_output": j.model_output,
                })
                if j.method == "llm_judge":
                    llm_call_count += 1

    # Calculate duration
    duration_seconds = time.time() - start_time

    # Aggregate by model
    model_stats = {}
    for r in all_results:
        model = r["model"]
        if model not in model_stats:
            model_stats[model] = {"match": 0, "no_match": 0, "error": 0, "total": 0}
        model_stats[model]["total"] += 1
        if r["judgment"] == "MATCH":
            model_stats[model]["match"] += 1
        elif r["judgment"] == "NO_MATCH":
            model_stats[model]["no_match"] += 1
        else:
            model_stats[model]["error"] += 1

    # Aggregate by field
    field_stats = {}
    for r in all_results:
        field = r["field"]
        if field not in field_stats:
            field_stats[field] = {"match": 0, "no_match": 0, "error": 0, "total": 0}
        field_stats[field]["total"] += 1
        if r["judgment"] == "MATCH":
            field_stats[field]["match"] += 1
        elif r["judgment"] == "NO_MATCH":
            field_stats[field]["no_match"] += 1
        else:
            field_stats[field]["error"] += 1

    # Calculate metrics (accuracy, precision, recall, F1)
    for stats in list(model_stats.values()) + list(field_stats.values()):
        _calculate_metrics(stats)

    # Calculate overall metrics
    overall_stats = {"match": 0, "no_match": 0, "error": 0, "total": 0}
    for r in all_results:
        overall_stats["total"] += 1
        if r["judgment"] == "MATCH":
            overall_stats["match"] += 1
        elif r["judgment"] == "NO_MATCH":
            overall_stats["no_match"] += 1
        else:
            overall_stats["error"] += 1
    _calculate_metrics(overall_stats)

    return {
        "eval_id": eval_id,
        "total_judgments": len(all_results),
        "llm_calls": llm_call_count,
        "duration_seconds": duration_seconds,
        "overall_stats": overall_stats,
        "model_stats": model_stats,
        "field_stats": field_stats,
        "details": all_results,
    }


def export_results_to_csv(results: dict, output_path: Path) -> None:
    """Export judgment results to CSV for human review.

    Columns:
    - contract: Contract filename
    - field: Field being evaluated
    - ground_truth: Human-annotated ground truth
    - model_output: Model's extracted value
    - model: Model that produced the extraction
    - method: Judgment method (empty_check, exact_match, llm_judge)
    - reasoning: Judge's reasoning
    - judgment: MATCH, NO_MATCH, or ERROR

    Args:
        results: Results dict from judge_eval_pairs().
        output_path: Path to write CSV file.
    """
    details = results.get("details", [])

    if not details:
        return

    # CSV columns in requested order
    fieldnames = [
        "contract",
        "field",
        "ground_truth",
        "model_output",
        "model",
        "method",
        "reasoning",
        "judgment",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in details:
            # Truncate long values for readability but keep full info
            writer.writerow({
                "contract": row["contract"],
                "field": row["field"],
                "ground_truth": row["ground_truth"],
                "model_output": row["model_output"],
                "model": row["model"],
                "method": row["method"],
                "reasoning": row["reasoning"],
                "judgment": row["judgment"],
            })


def fetch_langfuse_cost(eval_id: str, wait_seconds: int = 5) -> dict:
    """Fetch cost and token metrics from Langfuse for a judge run.

    Args:
        eval_id: The eval_id tag used for the judge run.
        wait_seconds: Seconds to wait for Langfuse ingestion.

    Returns:
        Dict with total_input_tokens, total_output_tokens, total_cost_usd.
    """
    if wait_seconds > 0:
        print(f"  Waiting {wait_seconds}s for Langfuse ingestion...")
        time.sleep(wait_seconds)

    langfuse = Langfuse()

    # Query traces with this eval_id tag
    # Note: Gemini traces may be captured via OpenInference instrumentation
    try:
        traces_response = langfuse.api.trace.list(limit=500, tags=[eval_id])
        traces = traces_response.data
    except Exception as e:
        return {
            "error": f"Failed to fetch traces: {e}",
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
        }

    if not traces:
        return {
            "trace_count": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_usd": 0.0,
            "note": "No traces found - Gemini may not be instrumented with Langfuse tags",
        }

    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    for trace in traces:
        try:
            observations = langfuse.api.observations.get_many(trace_id=trace.id)
            for obs in observations.data:
                if hasattr(obs, "usage_details") and obs.usage_details:
                    total_input_tokens += obs.usage_details.get("input", 0) or 0
                    total_output_tokens += obs.usage_details.get("output", 0) or 0
                if hasattr(obs, "cost_details") and obs.cost_details:
                    total_cost += obs.cost_details.get("total", 0) or 0
                elif hasattr(obs, "calculated_total_cost") and obs.calculated_total_cost:
                    total_cost += obs.calculated_total_cost
        except Exception:
            continue

    return {
        "trace_count": len(traces),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_cost_usd": total_cost,
    }


def create_judge_summary(
    results: dict,
    eval_pairs_file: str,
    langfuse_metrics: dict | None = None,
) -> dict:
    """Create a summary report for a judge evaluation run.

    Args:
        results: Results dict from judge_eval_pairs().
        eval_pairs_file: Path to the eval pairs file used.
        langfuse_metrics: Optional Langfuse cost metrics.

    Returns:
        Summary dict ready for JSON export.
    """
    summary = {
        "eval_id": results.get("eval_id"),
        "generated_at": datetime.now().isoformat(),
        "eval_pairs_file": eval_pairs_file,
        "run_info": {
            "total_judgments": results.get("total_judgments", 0),
            "llm_calls": results.get("llm_calls", 0),
            "duration_seconds": results.get("duration_seconds", 0),
        },
        "overall_metrics": results.get("overall_stats", {}),
        "model_metrics": results.get("model_stats", {}),
        "field_metrics": results.get("field_stats", {}),
    }

    if langfuse_metrics:
        summary["cost_metrics"] = langfuse_metrics

    return summary
