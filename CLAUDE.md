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

## Contract Intake API

FastAPI server for contract upload, extraction, and Airtable storage.

### API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/contracts/upload` | POST | Yes | Upload PDF, extract metadata, store in Airtable |
| `/contracts/{id}` | GET | Yes | Get contract by Airtable record ID |
| `/contracts/{id}/review` | PATCH | Yes | Mark contract as reviewed |
| `/contracts/{id}/fields` | PATCH | Yes | Update single field, log correction for ML training |
| `/contracts` | GET | Yes | List contracts (filter by `?status=under_review`) |
| `/health` | GET | No | Health check (public for Railway)

### Authentication

All `/contracts` endpoints require an API key via `X-API-Key` header:

```bash
curl -H "X-API-Key: YOUR_API_KEY" https://complyflow-production.up.railway.app/contracts
```

- Set `API_KEY` env var in Railway to enable authentication
- If `API_KEY` is not set, auth is disabled (local dev mode)

### Running the API

```bash
# Start development server
PYTHONPATH=src uv run uvicorn api.main:app --reload --port 8000

# Test upload
curl -X POST http://localhost:8000/contracts/upload \
  -F file=@cuad/train/contracts/01_service_gpaq.pdf
```

### Testing Components

```bash
# Test PDF extraction + Airtable connection
PYTHONPATH=src uv run python scripts/test_api.py

# Full pipeline test (extraction + date computation, ~60s)
PYTHONPATH=src uv run python scripts/test_api.py --full
```

## Airtable

**Base ID:** `appN3qGux4iVHtdU8`
**Table:** `Contracts`

### Schema (15 fields)

| Field | Type | Description |
|-------|------|-------------|
| filename | Text | Original PDF filename |
| parties | Long text | JSON array of party names |
| contract_type | Single select | One of 26 types (services, license, etc.) |
| agreement_date | Date | When signed |
| effective_date | Date | When takes effect |
| expiration_date | Date | When expires |
| expiration_type | Single select | absolute, perpetual, conditional |
| notice_deadline | Date | When to send renewal notice |
| first_renewal_date | Date | First auto-renewal date |
| governing_law | Text | Jurisdiction |
| notice_period | Text | Raw notice period |
| renewal_term | Long text | Renewal clause |
| status | Single select | under_review, reviewed |
| reviewed_at | Date | When reviewed |
| raw_extraction | Long text | Full extraction JSON |

### Corrections Table (ML Training Data)

Tracks human corrections to AI-extracted fields for building training datasets.

| Field | Type | Description |
|-------|------|-------------|
| field_name | Text | Primary field - which field was corrected |
| contract | Link | Links to Contracts table |
| original_value | Long text | AI-extracted value (JSON) |
| corrected_value | Long text | Human-corrected value (JSON) |
| corrected_at | DateTime | When correction was made |

### Setup (one-time)

```bash
# Create the Contracts table (already done)
PYTHONPATH=src uv run python -m api.setup_airtable
```

### Environment Variables

Required in `.env`:
```
AIRTABLE_API_KEY=patXXX...
AIRTABLE_BASE_ID=appN3qGux4iVHtdU8
SLACK_WEBHOOK_URL=https://hooks.slack.com/...  # Optional
```

## Langfuse Tracing

All LLM calls are traced in Langfuse for observability and cost tracking.

### Tags

| Tag | Description |
|-----|-------------|
| `source:api` | Calls originating from the Contract Intake API |
| `extraction` | Contract metadata extraction calls |
| `date-computation` | Date computation calls |
| `provider:openai` | OpenAI provider calls |
| `split:train` / `split:test` | Batch evaluation runs |

### Filtering API Usage

To see only API-originated token usage in Langfuse:
1. Go to Traces
2. Filter by tag: `source:api`

This separates API production usage from batch evaluation runs.

## Deployment

### Railway (Production)

**URL:** https://complyflow-production.up.railway.app

**Configuration files:**
- `Dockerfile` - Docker build config
- `railway.json` - Railway config (builder, start command, health checks)
- `requirements.txt` - Python dependencies (generated from `uv pip compile`)

**Deploy via CLI:**
```bash
# Install Railway CLI
brew install railway

# Login and link project
railway login
railway link

# Deploy
railway up --detach

# Check logs
railway logs -n 50        # Deploy logs
railway logs -b -n 50     # Build logs

# Redeploy
railway redeploy -y
```

**Environment variables (set in Railway dashboard):**
- `API_KEY` - API authentication key (required for production)
- `AIRTABLE_API_KEY`
- `AIRTABLE_BASE_ID`
- `OPENAI_API_KEY`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `SLACK_WEBHOOK_URL` (optional)

**Key learnings:**
- Use `railway.json` (not `.toml`) with `"builder": "DOCKERFILE"`
- Start command needs shell wrapper for `$PORT` expansion: `/bin/sh -c 'uvicorn ...'`
- Use `--loop asyncio` to avoid uvloop C extension issues in slim Docker images

## Tech Stack

- Python backend (uv for package management)
- API: FastAPI + uvicorn
- Deployment: Railway (Docker)
- Observability: Langfuse
- Vector store: TBD
- LLM: OpenAI GPT-5-mini (extraction + date computation)
- Database: Airtable
- Integrations: Airtable API, Slack API
- Frontend: TBD

## Commands

```bash
# Sync dependencies
uv sync

# Run scripts
uv run python script.py

# Start API server
PYTHONPATH=src uv run uvicorn api.main:app --reload --port 8000
```

## Claude Instructions

- When asked about current APIs, libraries, or technical solutions, proactively search online without being explicitly asked.
- Use Context7 MCP to look up current library documentation and usage examples.
- Use DeepWiki MCP to explore GitHub repositories and understand library architecture.
