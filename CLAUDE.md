# ComplyFlow - AI Legal & Compliance Platform

Case study implementation for Bit Capital: automated contract management and regulatory monitoring.

## Project Overview

Three main workflows:
1. **Contract Intake** - Upload PDFs, extract metadata, store in Airtable, Slack notifications
2. **Compliance Dashboard** - Contract aggregation, filters, Q&A chatbot with citations
3. **Regulatory Monitoring** - Daily web scraping (DORA, AML, AI, ESG, crypto), vector store, weekly summaries

## Test Data

`cuad/` contains 10 sample contracts from the CUAD dataset with ground truth labels in `metadata.json`.
Use these to validate extraction accuracy before building the full pipeline.

## Key Deliverables

- Modular source code (ingestion, vector-store, agent orchestration, API calls)
- Architecture doc with model selection rationale
- Extraction prompts with fallback strategies
- Final report: performance metrics, token usage analysis, cost-quality tradeoffs

## Extraction Schema

MVP schema in `src/extraction/schema.py` with 5 fields, all matching CUAD ground truth:

| Field | CUAD Ground Truth |
|-------|-------------------|
| `parties` | `Parties` |
| `contract_type` | `contract_type` (26 types in `cuad/contract_types.json`) |
| `notice_period` | `Notice Period To Terminate Renewal` |
| `expiration_date` | `Expiration Date` |
| `renewal_term` | `Renewal Term` |

**Deferred fields** (no CUAD ground truth, add later):
- `costs` - contract value/fees
- `jurisdiction` - governing law (CUAD has raw text, not normalized)
- `counterparty` - primary external party (redundant with parties for now)
- `risk` - manual assignment

## Architecture

### Modular Pipeline

The extraction pipeline is modular - each step is separate:

1. **PDF Text Extraction** (`src/extraction/pdf_text.py`)
   - Uses pdfplumber to extract text from PDFs
   - Pre-extracted text stored in `temp/extracted_text/*.txt`
   - Run once per PDF, reuse the text files

2. **LLM Extraction** (`src/extraction/extract_with_citations.py`)
   - Takes **text files** as input (NOT PDFs directly)
   - Sends to Anthropic API with citations enabled
   - Returns structured data with source citations

This separation keeps costs low - text extraction is free, and we only pay for the actual text tokens sent to the LLM (not raw PDF bytes).

### Pre-extracted Text Files

All CUAD contracts have been extracted to `temp/extracted_text/`:
- `01_service_gpaq.txt` through `10_outsourcing_paratek.txt`

Use these text files for LLM extraction, not the original PDFs.

## Current Work: Date Computation Pipeline

Working with **GPT-5-mini** extractions on 20 contracts (10 train + 10 test).

### Extraction Outputs

Primary extraction outputs are in `output/gpt-5-mini/`:
- 20 contracts extracted with GPT-5-mini (our model of choice)
- Format: `{nn}_{type}_{name}_extraction.json`

### Date Computation

Transforms extracted date fields into structured `{year, month, day}` objects:

| Output Field | Source |
|--------------|--------|
| `agreement_date` | Direct from extraction |
| `effective_date` | Direct from extraction |
| `expiration_date` | Computed (handles relative terms like "5 years from Effective Date") |
| `notice_deadline` | Derived: expiration - notice_period |
| `first_renewal_date` | Derived: equals expiration if auto-renewal exists |

**Run date computation:**
```bash
PYTHONPATH=src uv run python -m extraction.compute_dates \
  --extractions-dir output/gpt-5-mini \
  --split train \
  --no-code-interpreter
```

**Generate review table:**
```bash
PYTHONPATH=src uv run python -m extraction.date_review \
  --results-dir output/date_computation/<eval_id>_results \
  --output output/date_computation/train_review.csv \
  --format csv
```

## Tech Stack

- Python backend (uv for package management)
- Vector store: TBD
- LLM: OpenAI GPT-5-mini (extraction + date computation)
- Integrations: Airtable API, Slack API
- Frontend: TBD

## Commands

```bash
# Sync dependencies
uv sync

# Run scripts
uv run python script.py
```

## Claude Instructions

- When asked about current APIs, libraries, or technical solutions, proactively search online without being explicitly asked.
- Use Context7 MCP to look up current library documentation and usage examples.
- Use DeepWiki MCP to explore GitHub repositories and understand library architecture.
