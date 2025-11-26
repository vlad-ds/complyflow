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

## Tech Stack (TBD)

- Python backend (uv for package management)
- Vector store: TBD
- LLM: Claude (model tiering based on task complexity)
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
