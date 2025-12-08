# ComplyFlow

AI-powered legal and compliance platform for automated contract management and regulatory monitoring.

## Features

**Contract Intake Pipeline**
- Upload PDF contracts via REST API
- AI-powered metadata extraction (parties, dates, renewal terms, etc.)
- Automatic storage in Airtable with human review workflow
- Slack notifications for new uploads

**Compliance Dashboard**
- Contract aggregation with filters
- Q&A chatbot with citations from contract text
- Field-level corrections tracked for ML training

**Regulatory Monitoring (Regwatch)**
- Daily ingestion from EUR-Lex RSS feeds (DORA, MiCA, AIFMD, MiFID II, AML, AI Act, SFDR)
- Vector search over regulatory documents using Qdrant
- Materiality analysis for new regulations
- Weekly summary generation (JSON + PDF export)

## Setup

### 1. Install dependencies

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Or using pip:

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your API keys. Required services:

| Variable | Service | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI | Contract extraction (GPT-4) |
| `AIRTABLE_API_KEY` | Airtable | Contract storage |
| `AIRTABLE_BASE_ID` | Airtable | Database identifier |
| `LANGFUSE_*` | Langfuse | LLM observability & cost tracking |

Optional for full functionality:

| Variable | Service | Purpose |
|----------|---------|---------|
| `QDRANT_URL`, `QDRANT_API_KEY` | Qdrant Cloud | Vector search for regwatch |
| `JINA_API_KEY` | Jina.ai | EUR-Lex document fetching |
| `SLACK_WEBHOOK_URL` | Slack | Notifications |
| `BUCKET`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY` | Railway S3 | Document cache storage |

See `.env.example` for the complete list.

## Usage

### Run the API server

```bash
PYTHONPATH=src uv run uvicorn api.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`

### Upload a contract

```bash
curl -X POST http://localhost:8000/contracts/upload \
  -H "X-API-Key: YOUR_API_KEY" \
  -F file=@path/to/contract.pdf
```

### Run regulatory monitoring

```bash
# Fetch and index new regulatory documents
PYTHONPATH=src uv run python -m regwatch --verbose

# Dry run (no uploads)
PYTHONPATH=src uv run python -m regwatch --dry-run --verbose
```

## Project Structure

```
src/
  api/            # FastAPI endpoints for contract management
  alerts/         # Deadline notification service
  chatbot/        # Regulatory Q&A chatbot
  contracts/      # Contract data models
  contracts_chat/ # Contract Q&A with citations
  extraction/     # PDF parsing and metadata extraction
  llm/            # LLM provider abstractions (OpenAI, Gemini, Cohere)
  prompts/        # Prompt templates
  regwatch/       # Regulatory monitoring pipeline
  utils/          # Token counting, helpers

cuad/             # Test contracts from CUAD dataset
scripts/          # Utility scripts
```

## Deployment

The API is deployed on Railway. See `Dockerfile` and `railway.json` for configuration.

Production URL: `https://complyflow-production.up.railway.app`

## Tech Stack

- **Backend**: Python, FastAPI, uvicorn
- **LLM**: OpenAI GPT-4, Anthropic Claude, Google Gemini
- **Vector Store**: Qdrant Cloud
- **Database**: Airtable
- **Observability**: Langfuse
- **Deployment**: Railway (Docker)
- **Package Management**: uv
