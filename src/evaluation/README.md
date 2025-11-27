# Evaluation Module

Orchestrates contract metadata extraction across multiple LLM models and generates comparison reports with cost tracking.

## Architecture

```
evaluation/
├── __init__.py      # Public API exports
├── __main__.py      # CLI entry point
├── config.py        # Model configs and paths
├── runner.py        # Extraction logic (idempotent)
├── report.py        # Report generation + Langfuse metrics
└── README.md
```

## CLI Usage

```bash
# Run from src/ directory
cd src

# Extract with specific model (idempotent - skips existing)
python -m evaluation extract --models flash

# Extract with multiple models
python -m evaluation extract --models flash,haiku,gpt-5-mini

# Force re-extraction
python -m evaluation extract --models flash --force

# Generate report only (reads existing JSONs, queries Langfuse)
python -m evaluation report --models flash

# Skip Langfuse (faster, no cost data)
python -m evaluation report --models flash --no-langfuse

# Extract + report in one command
python -m evaluation all --models flash

# Run all configured models
python -m evaluation extract
```

## Available Models

Configured in `config.py`:

| Short Name | Provider | Full Model ID |
|------------|----------|---------------|
| `sonnet` | Anthropic | claude-sonnet-4-5-20250929 |
| `haiku` | Anthropic | claude-haiku-4-5-20251001 |
| `gpt-5` | OpenAI | gpt-5-2025-08-07 |
| `gpt-5-mini` | OpenAI | gpt-5-mini-2025-08-07 |
| `flash` | Gemini | gemini-2.5-flash |

## Output Structure

```
output/
├── flash/                          # Per-model extraction outputs
│   ├── 01_service_gpaq_extraction.json
│   └── ...
├── sonnet/
│   └── ...
├── run_summaries/                  # Comparison reports
│   └── comparison_train_20251127_150326.json
└── eval_pairs/                     # Ground truth pairs for accuracy eval
    └── train_eval_pairs.json
```

## Extraction JSON Schema

Each extraction output includes:

```json
{
  "source_file": "01_service_gpaq.txt",
  "provider": "gemini",
  "model": "flash",
  "eval_id": "eval_flash_20251127_150143_2f19796b",
  "timestamp": "2024-11-27T15:01:54.123456",
  "extraction": {
    "parties": { "raw_snippet": "...", "reasoning": "...", "normalized_value": [...] },
    "contract_type": { ... },
    "notice_period": { ... },
    "expiration_date": { ... },
    "renewal_term": { ... }
  },
  "usage": {
    "model": "gemini-2.5-flash",
    "input_tokens": 20108,
    "output_tokens": 643
  },
  "latency_seconds": 10.63
}
```

## Langfuse Integration

Each extraction is tagged in Langfuse with:
- `eval_id` - Unique run identifier (e.g., `eval_flash_20251127_150143_2f19796b`)
- `provider:{name}` - Provider tag
- `model:{name}` - Model tag

The report generator queries Langfuse by `eval_id` to aggregate:
- Total/average tokens
- Total/average cost (USD)
- Per-trace breakdown

## Idempotency

Extraction is idempotent:
- If an output JSON exists for a contract/model, it's skipped
- Use `--force` to re-extract
- Reports can be regenerated anytime from existing JSONs
