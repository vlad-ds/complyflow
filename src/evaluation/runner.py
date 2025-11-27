"""Evaluation runner - orchestrates extraction across models.

Extraction is idempotent: skips contracts that already have output JSONs.
Each extraction gets a unique eval_id tagged in Langfuse for cost tracking.
Reporting is separate - see report.py for aggregating metrics.
"""

import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from evaluation.config import (
    CUAD_TRAIN_METADATA,
    CUAD_TEST_METADATA,
    EVAL_MODELS,
    EXTRACTED_TEXT_TRAIN,
    EXTRACTED_TEXT_TEST,
    OUTPUT_DIR,
    ModelConfig,
)
from extraction.extract import extract_contract_metadata
from llm import get_provider


def _generate_eval_id(model: str) -> str:
    """Generate a unique evaluation ID for a model run."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"eval_{model}_{timestamp}_{short_uuid}"


def _get_text_path(contract_file: str, split: str = "train") -> Path:
    """Get the path to the extracted text file for a contract."""
    text_dir = EXTRACTED_TEXT_TRAIN if split == "train" else EXTRACTED_TEXT_TEST
    text_file = contract_file.replace(".pdf", ".txt")
    return text_dir / text_file


def _get_output_path(model_config: ModelConfig, contract_file: str) -> Path:
    """Get the path to the extraction output JSON for a model/contract."""
    output_dir = OUTPUT_DIR / model_config.output_folder
    output_file = contract_file.replace(".pdf", "_extraction.json")
    return output_dir / output_file


def _load_ground_truth(split: str = "train") -> list[dict]:
    """Load CUAD ground truth metadata for a split."""
    metadata_path = CUAD_TRAIN_METADATA if split == "train" else CUAD_TEST_METADATA
    if not metadata_path.exists():
        return []
    with open(metadata_path) as f:
        return json.load(f)


def _run_single_extraction(
    model_config: ModelConfig,
    text_path: Path,
    output_path: Path,
    eval_id: str,
) -> tuple[dict | None, float]:
    """Run extraction for a single contract with a single model.

    Returns tuple of (extraction_data, latency_seconds).
    extraction_data is None if extraction fails.
    """
    provider = get_provider(model_config.provider, model=model_config.model)

    print(f"    Extracting with {model_config.provider}/{model_config.model}...")

    start_time = time.time()
    try:
        result = extract_contract_metadata(
            provider, text_path, model=model_config.model, eval_id=eval_id
        )
        latency = time.time() - start_time

        # Build output JSON
        llm_resp = getattr(result, "_llm_response", None)
        output_data = {
            "source_file": text_path.name,
            "provider": model_config.provider,
            "model": model_config.model,
            "eval_id": eval_id,
            "timestamp": datetime.now().isoformat(),
            "extraction": {
                "parties": {
                    "raw_snippet": result.parties.raw_snippet,
                    "reasoning": result.parties.reasoning,
                    "normalized_value": result.parties.normalized_value,
                },
                "contract_type": {
                    "raw_snippet": result.contract_type.raw_snippet,
                    "reasoning": result.contract_type.reasoning,
                    "normalized_value": result.contract_type.normalized_value,
                },
                "notice_period": {
                    "raw_snippet": result.notice_period.raw_snippet,
                    "reasoning": result.notice_period.reasoning,
                    "normalized_value": result.notice_period.normalized_value,
                },
                "expiration_date": {
                    "raw_snippet": result.expiration_date.raw_snippet,
                    "reasoning": result.expiration_date.reasoning,
                    "normalized_value": result.expiration_date.normalized_value,
                },
                "renewal_term": {
                    "raw_snippet": result.renewal_term.raw_snippet,
                    "reasoning": result.renewal_term.reasoning,
                    "normalized_value": result.renewal_term.normalized_value,
                },
            },
            "usage": {
                "model": llm_resp.model if llm_resp else None,
                "input_tokens": llm_resp.input_tokens if llm_resp else None,
                "output_tokens": llm_resp.output_tokens if llm_resp else None,
            },
            "latency_seconds": latency,
        }

        # Save JSON
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"      Saved: {output_path.name} ({latency:.2f}s)")
        return output_data, latency

    except Exception as e:
        latency = time.time() - start_time
        print(f"      ERROR: {e} ({latency:.2f}s)")
        return None, latency


def run_model_extraction(
    model_config: ModelConfig,
    split: str = "train",
    force: bool = False,
) -> dict:
    """Run extraction for a single model across all contracts in a split.

    Idempotent: skips contracts that already have output JSONs unless force=True.
    Each new extraction gets tagged with a unique eval_id in Langfuse.

    Args:
        model_config: Model configuration to use.
        split: Dataset split ("train" or "test").
        force: If True, re-run even if outputs exist.

    Returns:
        Summary dict with counts of extracted/skipped/errors.
    """
    ground_truth = _load_ground_truth(split)
    if not ground_truth:
        print(f"No ground truth found for split '{split}'")
        return {}

    # Generate unique eval ID for this run
    eval_id = _generate_eval_id(model_config.model)
    print(f"\n{'='*60}")
    print(f"Model: {model_config.provider}/{model_config.model}")
    print(f"Eval ID: {eval_id}")
    print(f"Split: {split} ({len(ground_truth)} contracts)")
    print(f"{'='*60}")

    start_time = time.time()
    extracted_count = 0
    skipped_count = 0
    error_count = 0

    for contract in ground_truth:
        contract_file = contract["file"]
        text_path = _get_text_path(contract_file, split)

        if not text_path.exists():
            print(f"  WARNING: Text file not found: {text_path}")
            error_count += 1
            continue

        print(f"\n  Contract: {contract_file}")
        output_path = _get_output_path(model_config, contract_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if output already exists (idempotent)
        if output_path.exists() and not force:
            print(f"    Already exists, skipping")
            skipped_count += 1
            continue

        # Run extraction
        extraction_data, _ = _run_single_extraction(
            model_config, text_path, output_path, eval_id
        )
        if extraction_data:
            extracted_count += 1
        else:
            error_count += 1

    total_time = time.time() - start_time

    # Print summary
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE: {model_config.model}")
    print(f"{'='*60}")
    print(f"Extracted: {extracted_count}, Skipped: {skipped_count}, Errors: {error_count}")
    print(f"Total time: {total_time:.2f}s")
    if extracted_count > 0:
        print(f"Eval ID for this run: {eval_id}")

    return {
        "model": model_config.model,
        "provider": model_config.provider,
        "split": split,
        "eval_id": eval_id if extracted_count > 0 else None,
        "extracted": extracted_count,
        "skipped": skipped_count,
        "errors": error_count,
        "total_time": total_time,
    }


def run_extractions(
    models: list[ModelConfig] | None = None,
    split: str = "train",
    force: bool = False,
) -> list[dict]:
    """Run extractions for multiple models.

    Args:
        models: List of model configs. Defaults to EVAL_MODELS.
        split: Dataset split ("train" or "test").
        force: If True, re-run even if outputs exist.

    Returns:
        List of extraction summaries per model.
    """
    models = models or EVAL_MODELS
    summaries = []

    for model_config in models:
        summary = run_model_extraction(model_config, split, force)
        summaries.append(summary)

    return summaries
