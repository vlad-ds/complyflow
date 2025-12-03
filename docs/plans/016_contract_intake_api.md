# Plan 016: Contract Intake API

**Objective:** Build an API that accepts contract uploads, extracts metadata, computes dates, stores in Airtable, and triggers Slack notifications.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Contract Intake Flow                         │
└─────────────────────────────────────────────────────────────────────┘

  User uploads PDF
        │
        ▼
┌───────────────────┐
│   FastAPI Server  │  ← POST /contracts/upload
│   (Modal.com)     │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  PDF Text Extract │  ← pdfplumber (in-memory)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  LLM Extraction   │  ← OpenAI GPT-5-mini
│  (8 fields)       │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│ Date Computation  │  ← OpenAI GPT-5-mini
│ (5 computed)      │
└───────────────────┘
        │
        ├──────────────────────────────────┐
        ▼                                  ▼
┌───────────────────┐              ┌───────────────────┐
│    Airtable       │              │      Slack        │
│ (contracts table) │              │  (notification)   │
│ reviewed = false  │              │  "New contract    │
└───────────────────┘              │   needs review"   │
                                   └───────────────────┘
```

---

## 2. Deployment Options

### Option A: Modal.com (Recommended)

**Why Modal:**
- Serverless Python with zero infrastructure setup
- Native FastAPI support via `@modal.asgi_app()`
- Cold start ~2-3s, warm requests <100ms
- Pay-per-use pricing (~$0.001 per request for this workload)
- Dead simple deployment: `modal deploy`
- Built-in secrets management
- No VPC, API Gateway, or Lambda layers to configure

**Estimated setup time:** 1-2 hours

```python
# Example deployment
import modal

app = modal.App("complyflow-intake")

@app.function(secrets=[modal.Secret.from_name("complyflow-secrets")])
@modal.asgi_app()
def api():
    from api.main import app
    return app
```

### Option B: AWS API Gateway + Lambda

**Components:**
- API Gateway (REST API)
- Lambda function (Python 3.11)
- Lambda layers for dependencies (pdfplumber, openai, etc.)
- S3 bucket for temporary PDF storage
- IAM roles and policies

**Challenges:**
- Lambda has 250MB deployment limit (need layers)
- pdfplumber has native dependencies (may need container image)
- API Gateway + Lambda cold starts can be 5-10s
- More configuration overhead

**Estimated setup time:** 4-8 hours

### Option C: AWS Lambda Container Image

If Lambda is required:
- Build Docker image with all dependencies
- Push to ECR
- Lambda runs container
- Handles native deps (pdfplumber) cleanly

**Estimated setup time:** 3-5 hours

### Recommendation

**Go with Modal.com** for the MVP:
- Get something working in 1-2 hours
- Can migrate to AWS later if needed
- Same Python code works everywhere
- Focus on business logic, not infrastructure

---

## 3. API Design

### Endpoints

```
POST /contracts/upload
  - Accepts: multipart/form-data (PDF file)
  - Returns: Contract ID, extraction results, Airtable record ID
  - Side effects: Creates Airtable record, sends Slack notification

GET /contracts/{id}
  - Returns: Full contract record from Airtable

PATCH /contracts/{id}/review
  - Body: {"reviewed": true}
  - Returns: Updated record
  - Side effects: Updates Airtable status

GET /contracts
  - Query params: ?reviewed=true|false, ?limit=50
  - Returns: List of contracts from Airtable

GET /health
  - Returns: {"status": "ok", "version": "1.0.0"}
```

### Request/Response Models

```python
# POST /contracts/upload response
{
    "contract_id": "rec123abc",           # Airtable record ID
    "filename": "vendor_agreement.pdf",
    "extraction": {
        "parties": ["Acme Corp", "Vendor Inc"],
        "contract_type": "services",
        "agreement_date": {"year": 2024, "month": 1, "day": 15},
        "effective_date": {"year": 2024, "month": 2, "day": 1},
        "expiration_date": {"year": 2029, "month": 1, "day": 31},
        "governing_law": "Delaware",
        "notice_period": "90 days",
        "renewal_term": "1 year auto-renewal"
    },
    "computed_dates": {
        "agreement_date": {"year": 2024, "month": 1, "day": 15},
        "effective_date": {"year": 2024, "month": 2, "day": 1},
        "expiration_date": {"year": 2029, "month": 1, "day": 31},
        "notice_deadline": {"year": 2028, "month": 11, "day": 2},
        "first_renewal_date": {"year": 2029, "month": 1, "day": 31}
    },
    "status": "under_review",
    "created_at": "2024-01-15T10:30:00Z"
}
```

---

## 4. Airtable Schema

### Base: `ComplyFlow`
### Table: `Contracts`

| Field Name | Field Type | Description |
|------------|------------|-------------|
| `contract_id` | Autonumber | Primary key |
| `filename` | Single line text | Original PDF filename |
| `pdf_url` | URL | Link to stored PDF (Airtable attachment or S3) |
| `parties` | Long text | JSON array of party names |
| `contract_type` | Single select | One of 26 contract types |
| `agreement_date` | Date | When signed |
| `effective_date` | Date | When takes effect |
| `expiration_date` | Date | When expires (null if perpetual) |
| `expiration_type` | Single select | "absolute", "perpetual", "conditional" |
| `notice_deadline` | Date | When to send renewal notice |
| `first_renewal_date` | Date | First auto-renewal date |
| `governing_law` | Single line text | Jurisdiction |
| `notice_period` | Single line text | Raw notice period text |
| `renewal_term` | Long text | Renewal clause description |
| `status` | Single select | "under_review", "reviewed" |
| `reviewed_by` | Collaborator | Who reviewed it |
| `reviewed_at` | Date | When reviewed |
| `created_at` | Created time | Auto-generated |
| `raw_extraction` | Long text | Full extraction JSON for debugging |

### Views:
- **All Contracts** - Default view
- **Needs Review** - Filter: `status = "under_review"`
- **Upcoming Renewals** - Filter: `notice_deadline` in next 30 days, sorted by date

---

## 5. Slack Integration

### Notification Format

```
🆕 New Contract Uploaded

*Parties:* Acme Corp ↔ Vendor Inc
*Type:* Services Agreement
*Expires:* January 31, 2029
*Notice Deadline:* November 2, 2028

*Status:* Under Review

[Review Contract](https://airtable.com/app.../rec123) | [View PDF](https://...)
```

### Implementation

Use Slack Incoming Webhooks (simplest):
1. Create Slack App at api.slack.com
2. Enable Incoming Webhooks
3. Add webhook to `#compliance` channel
4. Store webhook URL in secrets

```python
import httpx

async def send_slack_notification(contract: dict, airtable_url: str):
    webhook_url = os.environ["SLACK_WEBHOOK_URL"]

    message = {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "🆕 New Contract Uploaded"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Parties:*\n{' ↔ '.join(contract['parties'])}"},
                {"type": "mrkdwn", "text": f"*Type:*\n{contract['contract_type']}"},
            ]},
            # ... more fields
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Review Contract"},
                 "url": airtable_url}
            ]}
        ]
    }

    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json=message)
```

---

## 6. Implementation Plan

### Phase 1: Core API (Day 1)

**Files to create:**
```
src/api/
  __init__.py
  main.py           # FastAPI app, routes
  models.py         # Pydantic request/response models
  services/
    __init__.py
    extraction.py   # Wraps existing extraction pipeline
    airtable.py     # Airtable client
    slack.py        # Slack notifications
```

**Step 1.1:** Create FastAPI app skeleton
```python
# src/api/main.py
from fastapi import FastAPI, UploadFile, HTTPException
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize clients on startup
    yield
    # Cleanup on shutdown

app = FastAPI(title="ComplyFlow Contract Intake", lifespan=lifespan)

@app.post("/contracts/upload")
async def upload_contract(file: UploadFile):
    ...

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
```

**Step 1.2:** Adapt existing extraction to work with in-memory PDFs
```python
# src/api/services/extraction.py
import io
import pdfplumber
from extraction.extract import extract_contract_metadata
from extraction.compute_dates import compute_dates_for_file

async def process_contract(pdf_bytes: bytes, filename: str) -> dict:
    # 1. Extract text from PDF bytes
    text = extract_text_from_bytes(pdf_bytes)

    # 2. Run LLM extraction
    extraction = await extract_contract_metadata_async(text)

    # 3. Compute dates
    computed_dates = await compute_dates_async(extraction)

    return {
        "filename": filename,
        "extraction": extraction,
        "computed_dates": computed_dates,
        "status": "under_review"
    }

def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n\n".join(page.extract_text() or "" for page in pdf.pages)
```

**Step 1.3:** Create Airtable client
```python
# src/api/services/airtable.py
import httpx
import os

class AirtableClient:
    def __init__(self):
        self.api_key = os.environ["AIRTABLE_API_KEY"]
        self.base_id = os.environ["AIRTABLE_BASE_ID"]
        self.table_name = "Contracts"
        self.base_url = f"https://api.airtable.com/v0/{self.base_id}/{self.table_name}"

    async def create_record(self, contract: dict) -> str:
        """Create a new contract record, return record ID."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"fields": self._to_airtable_fields(contract)}
            )
            response.raise_for_status()
            return response.json()["id"]

    async def update_record(self, record_id: str, fields: dict) -> dict:
        """Update an existing record."""
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{self.base_url}/{record_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"fields": fields}
            )
            response.raise_for_status()
            return response.json()

    def _to_airtable_fields(self, contract: dict) -> dict:
        """Convert contract dict to Airtable fields format."""
        # Airtable dates need ISO format: "2024-01-15"
        def date_to_iso(d):
            if d and isinstance(d, dict):
                return f"{d['year']}-{d['month']:02d}-{d['day']:02d}"
            return None

        return {
            "filename": contract["filename"],
            "parties": json.dumps(contract["extraction"]["parties"]),
            "contract_type": contract["extraction"]["contract_type"],
            "agreement_date": date_to_iso(contract["computed_dates"]["agreement_date"]),
            "effective_date": date_to_iso(contract["computed_dates"]["effective_date"]),
            "expiration_date": date_to_iso(contract["computed_dates"]["expiration_date"]),
            "notice_deadline": date_to_iso(contract["computed_dates"]["notice_deadline"]),
            "first_renewal_date": date_to_iso(contract["computed_dates"]["first_renewal_date"]),
            "governing_law": contract["extraction"]["governing_law"],
            "notice_period": contract["extraction"]["notice_period"],
            "renewal_term": contract["extraction"]["renewal_term"],
            "status": "under_review",
            "raw_extraction": json.dumps(contract, indent=2),
        }
```

### Phase 2: Slack Integration (Day 1)

**Step 2.1:** Create Slack notification service
```python
# src/api/services/slack.py
import httpx
import os

async def notify_new_contract(contract: dict, airtable_record_id: str):
    webhook_url = os.environ["SLACK_WEBHOOK_URL"]
    airtable_base_id = os.environ["AIRTABLE_BASE_ID"]

    # Build Airtable direct link
    airtable_url = f"https://airtable.com/{airtable_base_id}/Contracts/{airtable_record_id}"

    parties = contract["extraction"]["parties"]
    parties_str = " ↔ ".join(parties) if isinstance(parties, list) else str(parties)

    exp = contract["computed_dates"].get("expiration_date")
    exp_str = f"{exp['month']}/{exp['day']}/{exp['year']}" if exp else "Perpetual"

    notice = contract["computed_dates"].get("notice_deadline")
    notice_str = f"{notice['month']}/{notice['day']}/{notice['year']}" if notice else "N/A"

    message = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🆕 New Contract Uploaded", "emoji": True}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Parties:*\n{parties_str}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{contract['extraction']['contract_type']}"},
                    {"type": "mrkdwn", "text": f"*Expires:*\n{exp_str}"},
                    {"type": "mrkdwn", "text": f"*Notice Deadline:*\n{notice_str}"},
                ]
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"📄 `{contract['filename']}`"}
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Review in Airtable"},
                        "url": airtable_url,
                        "style": "primary"
                    }
                ]
            }
        ]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(webhook_url, json=message)
        response.raise_for_status()
```

### Phase 3: Deployment (Day 1-2)

**Step 3.1:** Create Modal deployment file
```python
# modal_app.py
import modal

app = modal.App("complyflow-intake")

# Create image with all dependencies
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "fastapi",
    "uvicorn",
    "pdfplumber",
    "openai>=2.8.1",
    "httpx",
    "python-multipart",  # For file uploads
    "langfuse",
)

@app.function(
    image=image,
    secrets=[modal.Secret.from_name("complyflow-secrets")],
    timeout=300,  # 5 min timeout for LLM calls
)
@modal.asgi_app()
def api():
    from src.api.main import app
    return app
```

**Step 3.2:** Configure secrets in Modal
```bash
# Set up secrets (one-time)
modal secret create complyflow-secrets \
    OPENAI_API_KEY=sk-... \
    AIRTABLE_API_KEY=pat... \
    AIRTABLE_BASE_ID=app... \
    SLACK_WEBHOOK_URL=https://hooks.slack.com/...
```

**Step 3.3:** Deploy
```bash
modal deploy modal_app.py
# Returns: https://complyflow-intake--api.modal.run
```

### Phase 4: Testing & Polish (Day 2)

**Step 4.1:** Local development server
```bash
# Run locally for testing
PYTHONPATH=src uvicorn src.api.main:app --reload --port 8000
```

**Step 4.2:** Test with curl
```bash
# Upload a test contract
curl -X POST "http://localhost:8000/contracts/upload" \
  -F "file=@cuad/01_service_gpaq.pdf"

# Check health
curl "http://localhost:8000/health"
```

**Step 4.3:** Add error handling and logging
- Wrap LLM calls in try/except
- Add Langfuse tracing to API endpoints
- Return meaningful error messages

---

## 7. Environment Variables

```bash
# LLM
OPENAI_API_KEY=sk-...

# Airtable
AIRTABLE_API_KEY=pat...          # Personal access token
AIRTABLE_BASE_ID=app...          # Base ID from URL

# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Langfuse (optional, for tracing)
LANGFUSE_SECRET_KEY=sk-...
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 8. Airtable Setup Instructions

1. Go to [airtable.com](https://airtable.com) and create a new base called "ComplyFlow"
2. Create a table called "Contracts" with the fields from Section 4
3. Get your API credentials:
   - Go to [airtable.com/create/tokens](https://airtable.com/create/tokens)
   - Create a personal access token with `data.records:read` and `data.records:write` scopes
   - Select the ComplyFlow base
4. Get your Base ID from the URL: `https://airtable.com/app.../...` → the `app...` part

---

## 9. Slack Setup Instructions

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and create a new app
2. Click "Incoming Webhooks" → Enable
3. Click "Add New Webhook to Workspace"
4. Select the `#compliance` channel (or create one)
5. Copy the webhook URL

---

## 10. File Structure After Implementation

```
src/
  api/
    __init__.py
    main.py                 # FastAPI app, routes
    models.py               # Request/response Pydantic models
    services/
      __init__.py
      extraction.py         # Contract processing pipeline
      airtable.py           # Airtable CRUD operations
      slack.py              # Slack notifications
  extraction/               # (existing)
  llm/                      # (existing)
  prompts/                  # (existing)

modal_app.py                # Modal deployment config
```

---

## 11. Cost Estimates

### Per Contract Upload

| Component | Cost |
|-----------|------|
| OpenAI GPT-5-mini extraction | ~$0.02 (15k input, 2.5k output tokens) |
| OpenAI GPT-5-mini date computation | ~$0.005 (1k input, 500 output tokens) |
| Modal compute | ~$0.001 (5s @ $0.0001/s) |
| Airtable | Free tier (1,200 records/base) |
| Slack | Free |
| **Total per upload** | **~$0.03** |

### Monthly (100 contracts/month)
- LLM costs: ~$3
- Modal: ~$0.10
- **Total: ~$3.10/month**

---

## 12. Future Enhancements (Out of Scope for MVP)

1. **PDF Storage** - Store PDFs in S3 or Airtable attachments
2. **Authentication** - Add API key auth or OAuth
3. **Bulk Upload** - Process multiple PDFs at once
4. **Retry Logic** - Queue failed extractions for retry
5. **Scheduled Reminders** - Use Modal cron jobs for renewal notifications
6. **Frontend** - Simple React/Next.js upload form

---

## 13. Decision Log

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| Deployment | Modal.com | Fastest to production, native Python, pay-per-use |
| Database | Airtable only | Case study requirement, no need for separate DB |
| Slack integration | Webhooks | Simplest approach, no OAuth needed |
| PDF storage | Not MVP | Add later if needed |
| Auth | Not MVP | Internal tool, add later |
