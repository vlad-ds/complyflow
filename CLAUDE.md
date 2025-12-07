# ComplyFlow - AI Legal & Compliance Platform

Case study implementation for Bit Capital: automated contract management and regulatory monitoring.

## Development Philosophy

This is a **greenfield project** for a take-home assessment. Priorities:
- **Simple, modular code** over complex abstractions
- **No migrations or backwards compatibility** - delete and recreate as needed
- **Clean architecture** that's easy to understand and extend

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
| `/contracts/{id}/citations` | GET | Yes | Get quotes and reasoning for each extracted field |
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

### Citations Table (Quotes, Reasoning & AI Values)

Stores the exact PDF quotes, AI reasoning, and original AI-extracted values for each field. Created automatically when a contract is uploaded.

| Field | Type | Description |
|-------|------|-------------|
| field_name | Text | Which field this citation is for (parties, contract_type, etc.) |
| contract | Link | Links to Contracts table |
| quote | Long text | Exact verbatim text from the PDF |
| reasoning | Long text | AI's explanation of how the value was interpreted |
| ai_value | Long text | AI's original extracted value (JSON string) |

This table preserves the AI's original interpretation even after human edits. The frontend can show:
- **AI value** (from `ai_value`) - what the AI extracted
- **Current value** (from Contracts table) - possibly human-edited
- **Quote + Reasoning** - why the AI made that interpretation

Use the `/contracts/{id}/citations` endpoint to retrieve citations for a contract.

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
FRONTEND_URL=https://your-app.lovable.app  # For Slack review button
```

## Langfuse Tracing

All LLM calls are traced in Langfuse for observability and cost tracking.

### Cost Tracking Policy

**All LLM calls MUST go through Langfuse.** This is required for accurate cost tracking.

How to ensure proper cost tracking:
1. Use the existing providers in `src/llm/` (OpenAIProvider, GeminiProvider, etc.)
2. These providers use instrumentors that auto-trace to Langfuse
3. Always set a Langfuse tag to identify the source (e.g., `regwatch-eval`, `source:api`)
4. Query Langfuse to get actual costs - never hardcode pricing estimates

To verify costs after a run:
```python
from langfuse_client import get_traces_by_tag, get_trace_summary

# Get traces for a specific tag
traces = get_traces_by_tag("regwatch-eval", limit=100)

# Get cost summary for a trace
summary = get_trace_summary(trace_id)
print(f"Cost: ${summary['total_cost']:.6f}")
```

### Tags

| Tag | Description |
|-----|-------------|
| `source:api` | Calls originating from the Contract Intake API |
| `extraction` | Contract metadata extraction calls |
| `date-computation` | Date computation calls |
| `provider:openai` | OpenAI provider calls |
| `provider:gemini` | Google Gemini provider calls |
| `provider:cohere` | Cohere provider calls |
| `split:train` / `split:test` | Batch evaluation runs |
| `regwatch-eval` | Regwatch RAG generation evaluation |

### Filtering API Usage

To see only API-originated token usage in Langfuse:
1. Go to Traces
2. Filter by tag: `source:api`

This separates API production usage from batch evaluation runs.

## Deadline Alerts

Standalone service to check for impending contract deadlines and send Slack notifications.

**Module:** `src/alerts/deadlines.py`

### Deadline Fields Monitored

| Field | Description |
|-------|-------------|
| `expiration_date` | Contract expiration |
| `notice_deadline` | Deadline to send renewal notice |
| `first_renewal_date` | First auto-renewal date |

### Alert Windows

Alerts are sent when a deadline is exactly:
- **30 days away** (1 month warning)
- **7 days away** (1 week warning)

### Usage

```bash
# Run deadline check with Slack notifications
PYTHONPATH=src uv run python -m alerts.deadlines

# Dry run (list without sending)
PYTHONPATH=src uv run python -m alerts.deadlines --dry-run

# Check for a specific date (testing)
PYTHONPATH=src uv run python -m alerts.deadlines --date 2024-12-15
```

### Railway Cron Job

To run daily at 9 AM UTC:

1. In Railway dashboard, create a new "Cron Job" service
2. Use the same Docker image as the main service
3. Set schedule: `0 9 * * *` (daily at 9 AM UTC)
4. Set start command: `python -m alerts.deadlines`
5. Add environment variables: `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID`, `SLACK_WEBHOOK_URL`

Alternatively, use an external scheduler (e.g., cron-job.org) to run the script.

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
- `FRONTEND_URL` - Frontend app URL for Slack review button (e.g., `https://your-app.lovable.app`)

**Key learnings:**
- Use `railway.json` (not `.toml`) with `"builder": "DOCKERFILE"`
- Start command needs shell wrapper for `$PORT` expansion: `/bin/sh -c 'uvicorn ...'`
- Use `--loop asyncio` to avoid uvloop C extension issues in slim Docker images

## Regwatch (Regulatory Monitoring)

Module for fetching EU regulatory documents from EUR-Lex RSS feeds.

**Module:** `src/regwatch/`

### Architecture

```
src/regwatch/
├── config.py              # RSS feeds, retry settings, Jina config
├── storage.py             # S3/local storage abstraction
└── connectors/
    ├── base.py            # BaseConnector, Document dataclass
    └── eurlex.py          # EUR-Lex RSS + Jina.ai full-text extraction
```

### How It Works

1. **RSS Feeds**: 7 pre-configured feeds (DORA, MiCA, AIFMD, MiFID II, AML, AI Act, SFDR)
2. **Full-text Extraction**: Uses Jina.ai Reader API to bypass EUR-Lex WAF
3. **Storage**: S3 on Railway, local filesystem for development
4. **Caching**: Documents cached to avoid re-downloading

### Key Jina.ai Headers (for WAF bypass)

```python
headers = {
    "X-Proxy-Url": "true",           # Proxy mode for WAF bypass
    "X-Wait-For-Selector": "#document1",  # Wait for content to load
    "X-Timeout": "60",               # Long timeout for WAF challenge
    "X-No-Cache": "true",            # Bypass cached failures
}
```

### Daily Ingestion Pipeline

Automated pipeline to fetch new documents, chunk, embed, and index to Qdrant.

**Module:** `src/regwatch/ingest.py`

**Configuration:** `src/regwatch/ingest_config.py`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `feeds` | `["DORA", "MiCA"]` | RSS feeds to process |
| `recent_docs_limit` | `5` | Max docs per feed |
| `lookback_days` | `30` | Only fetch docs from last N days |
| `chunk_size` | `2048` | Characters per chunk |
| `chunk_overlap` | `200` | Overlap between chunks |

**Run locally:**
```bash
# Dry run (fetch and process, but don't upload to Qdrant)
PYTHONPATH=src uv run python -m regwatch --dry-run --verbose

# Real run
PYTHONPATH=src uv run python -m regwatch --verbose

# With custom settings
PYTHONPATH=src uv run python -m regwatch --recent-docs-limit 10 --lookback-days 60
```

**Key features:**
- Registry (in S3) is source of truth for fully-indexed documents
- Deterministic point IDs (`{celex}_chunk_{index}`) for idempotent upserts
- Partial failure recovery: re-run re-uploads all chunks for incomplete documents

### Environment Variables

```
JINA_API_KEY=jina_xxx...           # Jina.ai API key (higher rate limits)
QDRANT_URL=https://xxx.qdrant.io   # Qdrant Cloud URL
QDRANT_API_KEY=xxx                 # Qdrant API key
BUCKET=regwatch-xxx                # Railway bucket name
ACCESS_KEY_ID=xxx                  # Railway S3 access key
SECRET_ACCESS_KEY=xxx              # Railway S3 secret
ENDPOINT=https://storage.railway.app
REGION=auto
```

## Railway S3 Bucket

Railway provides S3-compatible storage via Buckets.

### Accessing Bucket Contents

Railway CLI doesn't have bucket commands. Use AWS CLI with credentials from `.env`:

```bash
# Load credentials and list bucket
source .env
AWS_ACCESS_KEY_ID=$ACCESS_KEY_ID \
AWS_SECRET_ACCESS_KEY=$SECRET_ACCESS_KEY \
aws s3 ls s3://$BUCKET/regwatch/cache/ --endpoint-url $ENDPOINT
```

**Shell alias** (added to `~/.zshrc`):
```bash
alias s3-railway='AWS_ACCESS_KEY_ID=$ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY=$SECRET_ACCESS_KEY aws s3 --endpoint-url $ENDPOINT'

# Usage:
source .env
s3-railway ls s3://$BUCKET/regwatch/cache/
```

### Creating a Bucket

1. Go to Railway dashboard → your project
2. Click **Create** → **Bucket**
3. Name it (e.g., `regwatch`)
4. Link to your service - env vars are auto-injected

## Tech Stack

- Python backend (uv for package management)
- API: FastAPI + uvicorn
- Deployment: Railway (Docker)
- Storage: Railway Buckets (S3-compatible)
- Observability: Langfuse
- Vector store: TBD
- LLM: OpenAI GPT-5-mini (extraction + date computation)
- Database: Airtable
- Integrations: Airtable API, Slack API, Jina.ai Reader API
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

### Report Write-ups

When asked for a "short write-up" or "write-up for report", produce text for a technical assessment report:

- **Context**: This is a take-home assessment for Bit Capital. The report documents implementation decisions, methodology, and results.
- **Format**: Plain text suitable for Google Docs. No markdown tables (use prose instead). No code blocks unless specifically requested.
- **Length**: 2-4 paragraphs per topic. Concise but substantive.
- **Tone**: Professional, technical, third-person ("we implemented", "the system uses").
- **Content**: What was built, why (rationale), how it works, key metrics/results, limitations or future improvements.
- **Audience**: Technical reviewers evaluating the assessment submission.
