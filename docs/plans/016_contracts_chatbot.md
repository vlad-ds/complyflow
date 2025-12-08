# Plan: Contracts Chatbot (ContractBot)

## Overview

Build a Q&A chatbot for the compliance team to ask questions about contracts. The chatbot answers questions based on both **structured metadata** (from Airtable) and **unstructured content** (from Qdrant vector store).

**Key features:**
- Uses Claude Sonnet 4.5 with Code Execution Tool for data analysis
- Airtable contracts exported as CSV and loaded via Files API
- Custom Qdrant search tool for contract content retrieval
- Search results feature for proper citations from Qdrant chunks
- Full Langfuse tracing with `contracts-chat` tag

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     ContractBot Chat                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌───────────────────────────────────┐  │
│  │ Airtable     │ -> │ CSV File (uploaded via Files API) │  │
│  │ Contracts    │    │ - Loaded at chat init              │  │
│  └──────────────┘    │ - Code Execution for analysis     │  │
│                      └───────────────────────────────────┘  │
│                                                              │
│  ┌──────────────┐    ┌───────────────────────────────────┐  │
│  │ Qdrant       │ <- │ Custom Tool: search_contracts     │  │
│  │ Contracts    │    │ - Semantic search on content      │  │
│  │ Collection   │    │ - Returns search_result blocks    │  │
│  └──────────────┘    └───────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Claude Sonnet 4.5                                     │   │
│  │ - Code Execution Tool (analyze CSV)                   │   │
│  │ - search_contracts Tool (query Qdrant)                │   │
│  │ - Search Results for citations                        │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Claude API Features Used

### 1. Files API
- **Purpose**: Load Airtable contracts CSV for code execution
- **Beta header**: `files-api-2025-04-14`
- **Usage**: Upload CSV at chat initialization, reference by `file_id`
- **Content block type**: `container_upload` (for code execution access)

### 2. Code Execution Tool
- **Purpose**: Analyze structured contract data (counts, filters, dates)
- **Beta header**: `code-execution-2025-08-25`
- **Tool type**: `code_execution_20250825`
- **Use cases**:
  - "How many contracts expire in Q1 2025?"
  - "List all contracts with notice deadlines in the next 2 weeks"
  - "Which contracts are under review?"
  - "Show me contracts by type breakdown"

### 3. Custom Tool: `search_contracts`
- **Purpose**: Semantic search on contract content in Qdrant
- **Implementation**: Server-side tool that queries Qdrant
- **Returns**: `search_result` content blocks with citations enabled
- **Use cases**:
  - "What does the ACME contract say about termination?"
  - "Find clauses about indemnification"
  - "What are the payment terms in contract X?"

### 4. Search Results with Citations
- **Purpose**: Enable Claude to cite Qdrant chunks properly
- **Content block type**: `search_result`
- **Fields**: `source`, `title`, `content`, `citations.enabled`
- **Citation format**: `search_result_location` with `source`, `title`, `cited_text`

## Module Structure

```
src/contracts_chat/
├── __init__.py
├── chat.py              # Main chat orchestration
├── airtable_export.py   # Export contracts to CSV
├── tools.py             # search_contracts tool definition & handler
└── prompts/
    └── contracts_system_v1.md  # System prompt for Claude
```

## Implementation Steps

### Step 1: Airtable Export Module (`airtable_export.py`)

Export all contracts from Airtable to CSV format suitable for data analysis.

```python
def export_contracts_csv() -> str:
    """
    Export all contracts from Airtable to CSV string.

    Columns:
    - record_id, filename, parties, contract_type
    - agreement_date, effective_date, expiration_date
    - expiration_type, notice_deadline, first_renewal_date
    - governing_law, notice_period, renewal_term, status

    Returns:
        CSV string ready for upload to Files API
    """
```

### Step 2: Search Tool Definition (`tools.py`)

Define the custom tool for Qdrant search.

```python
SEARCH_CONTRACTS_TOOL = {
    "name": "search_contracts",
    "description": """Search contract documents for specific content.

    Use this tool when the user asks about:
    - Specific clauses or terms in contracts
    - What a particular contract says about a topic
    - Finding contracts that mention certain terms
    - Contract content that isn't in the metadata

    Do NOT use this for:
    - Counting contracts (use code execution instead)
    - Filtering by dates or status (use code execution instead)
    - Questions answerable from the CSV metadata
    """,
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query for contract content"
            },
            "contract_id": {
                "type": "string",
                "description": "Optional: Filter to a specific contract by Airtable record ID"
            }
        },
        "required": ["query"]
    }
}

def handle_search_contracts(query: str, contract_id: str | None = None) -> list[dict]:
    """
    Execute Qdrant search and return search_result blocks.

    Returns list of search_result dicts with citations enabled.
    """
```

### Step 3: Main Chat Module (`chat.py`)

Orchestrate the chat with Claude Sonnet 4.5.

```python
@observe(name="contracts-chat")
def chat(
    query: str,
    history: list[ChatMessage] | None = None,
    contracts_file_id: str | None = None,
) -> ChatResult:
    """
    Main chat function for contracts Q&A.

    Args:
        query: User's question
        history: Conversation history
        contracts_file_id: Pre-uploaded CSV file_id (optional, will export fresh if None)

    Returns:
        ChatResult with answer, sources, and usage
    """
```

**Chat flow:**
1. If no `contracts_file_id`, export Airtable to CSV and upload via Files API
2. Build messages with:
   - System prompt (contracts context, instructions)
   - Conversation history
   - User query with `container_upload` reference to CSV
3. Call Claude with tools:
   - `code_execution_20250825` for CSV analysis
   - `search_contracts` for content search
4. Handle tool use loop:
   - If `search_contracts` called: execute Qdrant search, return `search_result` blocks
   - If code execution: let Claude handle it server-side
5. Return final answer with citations

### Step 4: System Prompt (`prompts/contracts_system_v1.md`)

```markdown
You are a contracts assistant for BIT Capital's compliance team.

## Available Data

1. **Contracts CSV** (attached as file)
   - Contains structured metadata for all contracts
   - Columns: record_id, filename, parties, contract_type, dates, status, etc.
   - Use code execution to analyze this data

2. **Contract Content Search** (search_contracts tool)
   - Full text of contract documents is searchable
   - Returns relevant excerpts with citations
   - Use when asked about specific clauses or terms

## When to Use Each

**Use Code Execution** for:
- Counting contracts ("How many contracts expire in Q1?")
- Date calculations ("Renewals in next 2 weeks")
- Filtering and grouping ("Contracts by type")
- Status queries ("Which are under review?")

**Use search_contracts Tool** for:
- Clause content ("What does contract X say about termination?")
- Finding specific terms ("Which contracts mention arbitration?")
- Quote requests ("Show me the renewal clause")

## Response Format

- Always cite sources when quoting contract content
- For structured data, show the relevant data or calculation
- Be specific about which contracts you're referring to
```

### Step 5: API Endpoint

Add endpoint to `src/api/main.py`:

```python
@app.post("/contracts/chat")
async def contracts_chat(body: ContractsChatRequest):
    """
    Q&A chatbot for contracts.

    Answers questions about:
    - Structured metadata (counts, dates, filters)
    - Contract content (clauses, terms, specific text)

    Sources are cited in both cases.
    """
```

### Step 6: Langfuse Tracing

All calls traced with:
- **Tag**: `contracts-chat`
- **Metadata**: query, history_length, tools_used
- **Sub-traces**: `csv-upload`, `qdrant-search`, `generation`

## API Response Format

```python
class ContractsChatResponse(BaseModel):
    answer: str
    sources: list[ContractSource]  # From Qdrant search results
    data_sources: list[str] | None  # CSV columns/analysis used
    usage: dict | None

class ContractSource(BaseModel):
    contract_id: str
    filename: str
    text: str  # Cited excerpt
    score: float
```

## Environment Variables

Required (already configured):
- `ANTHROPIC_API_KEY` - Claude API
- `QDRANT_URL`, `QDRANT_API_KEY` - Vector store
- `AIRTABLE_API_KEY`, `AIRTABLE_BASE_ID` - Contracts data
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` - Tracing

## Testing Plan

### Local Testing
1. Export contracts CSV manually, verify format
2. Test Qdrant search tool in isolation
3. Test full chat flow with sample queries:
   - "How many contracts expire in the next month?"
   - "What does the GPAQ contract say about renewal?"
   - "List all service agreements under review"

### Integration Testing
1. Deploy to Railway
2. Test via API with real queries
3. Verify Langfuse traces show correct tags
4. Check citation format in responses

## Example Queries & Expected Behavior

| Query | Expected Approach |
|-------|-------------------|
| "How many contracts are under review?" | Code execution on CSV |
| "Which contracts expire in Q1 2025?" | Code execution with date filtering |
| "What are the termination terms in contract X?" | search_contracts tool |
| "Find all contracts mentioning arbitration" | search_contracts tool |
| "Show renewal deadlines for next 2 weeks" | Code execution with date math |
| "What does the ACME agreement say about liability?" | search_contracts tool |

## Files to Create/Modify

### New Files
1. `src/contracts_chat/__init__.py`
2. `src/contracts_chat/chat.py`
3. `src/contracts_chat/airtable_export.py`
4. `src/contracts_chat/tools.py`
5. `src/prompts/contracts_system_v1.md`

### Modified Files
1. `src/api/main.py` - Add `/contracts/chat` endpoint
2. `src/api/models.py` - Add request/response models

## Open Questions

1. **Container reuse**: Should we reuse the same container across chat turns, or create fresh for each request? Fresh is simpler but slower.
   - **Decision**: Start with fresh container per request; optimize later if needed

2. **CSV caching**: Should we cache the exported CSV, or export fresh each request?
   - **Decision**: Export fresh each request initially (data is small, ensures freshness)

3. **History handling**: How much history to send to Claude?
   - **Decision**: Last 10 messages, similar to regwatch chatbot

## Implementation Order

1. `airtable_export.py` - Export CSV function
2. `tools.py` - Search tool definition and handler
3. `chat.py` - Main chat orchestration
4. `src/prompts/contracts_system_v1.md` - System prompt
5. API models in `models.py`
6. API endpoint in `main.py`
7. Local testing
8. Railway deployment
