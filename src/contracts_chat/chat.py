"""
Contracts chatbot using Claude Sonnet 4.5.

Combines:
- Code Execution Tool for structured data analysis (Airtable CSV)
- Custom search_contracts tool for semantic search (Qdrant)
- Search Results feature for proper citations
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from langfuse import get_client, observe
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

from contracts_chat.airtable_export import export_contracts_csv
from contracts_chat.tools import (
    SEARCH_CONTRACTS_TOOL,
    format_tool_result_for_claude,
    handle_search_contracts,
)

load_dotenv()

logger = logging.getLogger(__name__)

# Initialize Anthropic instrumentation for Langfuse tracing
_instrumentor = AnthropicInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument()

# Prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Beta headers for Files API and Code Execution
BETA_HEADERS = ["files-api-2025-04-14", "code-execution-2025-08-25"]

# Model to use
MODEL = "claude-sonnet-4-5-20250929"


def _load_prompt(name: str) -> str:
    """Load a prompt from the prompts directory."""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text()


@dataclass
class ChatMessage:
    """A message in the conversation history."""

    role: str  # "user" or "assistant"
    content: str


@dataclass
class ContractSource:
    """A source from contract content search."""

    contract_id: str
    filename: str
    text: str
    score: float


@dataclass
class ToolUseEvent:
    """A tool use event from Claude's processing."""

    tool_name: str
    input_summary: str
    output_summary: str
    timestamp: str


@dataclass
class ChatResult:
    """Result from the chat function."""

    answer: str
    sources: list[ContractSource] = field(default_factory=list)
    tool_uses: list[ToolUseEvent] = field(default_factory=list)
    usage: dict | None = None


# Singleton client
_anthropic_client: anthropic.Anthropic | None = None


def _get_anthropic() -> anthropic.Anthropic:
    """Get or create Anthropic client."""
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


def _upload_csv_file(client: anthropic.Anthropic, csv_content: str) -> str:
    """
    Upload CSV content to Anthropic Files API.

    Args:
        client: Anthropic client
        csv_content: CSV string to upload

    Returns:
        file_id for use in messages
    """
    file_response = client.beta.files.upload(
        file=(
            "contracts.csv",
            csv_content.encode("utf-8"),
            "text/csv",
        ),
    )
    logger.info(f"Uploaded contracts CSV, file_id: {file_response.id}")
    return file_response.id


def _extract_answer_and_citations(content_blocks: list) -> tuple[str, list[dict]]:
    """
    Extract text content and citations from Claude's response.

    Returns:
        Tuple of (answer_text, citations_list)
        Each citation has: source, title, cited_text, search_result_index
    """
    text_parts = []
    all_citations = []
    seen_sources = set()  # Deduplicate citations by source

    for block in content_blocks:
        if hasattr(block, "type"):
            if block.type == "text":
                text_parts.append(block.text)
                # Extract citations from this text block
                if hasattr(block, "citations") and block.citations:
                    for citation in block.citations:
                        source = getattr(citation, "source", "") or ""
                        if source and source not in seen_sources:
                            seen_sources.add(source)
                            all_citations.append({
                                "source": source,
                                "title": getattr(citation, "title", "") or "",
                                "cited_text": getattr(citation, "cited_text", "") or "",
                                "search_result_index": getattr(citation, "search_result_index", 0),
                            })

    return "\n".join(text_parts), all_citations


def _handle_tool_use(tool_name: str, tool_input: dict) -> list[dict]:
    """
    Handle a tool use request from Claude.

    Args:
        tool_name: Name of the tool called
        tool_input: Input arguments for the tool

    Returns:
        Tool result content (list of content blocks)
    """
    if tool_name == "search_contracts":
        query = tool_input.get("query", "")
        contract_id = tool_input.get("contract_id")

        logger.info(f"Handling search_contracts: query='{query[:50]}...', contract_id={contract_id}")

        search_results = handle_search_contracts(
            query=query,
            contract_id=contract_id,
            top_k=20,
        )
        return format_tool_result_for_claude(search_results)
    else:
        # Unknown tool - return error
        return [{"type": "text", "text": f"Unknown tool: {tool_name}"}]


@observe(name="contracts-chat")
def chat(
    query: str,
    history: list[ChatMessage] | None = None,
) -> ChatResult:
    """
    Main chat function for contracts Q&A.

    Uses Claude Sonnet 4.5 with:
    - Code Execution Tool for CSV analysis
    - search_contracts tool for content search

    Args:
        query: User's question
        history: Conversation history (optional)

    Returns:
        ChatResult with answer, sources, and usage
    """
    history = history or []

    # Update Langfuse trace
    langfuse = get_client()
    langfuse.update_current_trace(
        name="contracts-chat",
        tags=["contracts-chat"],
        metadata={"query": query, "history_length": len(history)},
    )

    client = _get_anthropic()

    # Step 1: Export contracts to CSV and upload
    logger.info("Exporting contracts to CSV...")
    csv_content = export_contracts_csv()
    file_id = _upload_csv_file(client, csv_content)

    # Step 2: Build system prompt with current date
    from datetime import date
    system_prompt = _load_prompt("contracts_chat_system_v1").format(
        current_date=date.today().isoformat()
    )

    # Step 3: Build messages
    messages = []

    # Add conversation history (last 10 messages)
    for msg in history[-10:]:
        messages.append({"role": msg.role, "content": msg.content})

    # Add current user message with file reference
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": query},
                {
                    "type": "container_upload",
                    "file_id": file_id,
                },
            ],
        }
    )

    # Step 4: Define tools
    tools = [
        # Code execution tool (Anthropic-managed)
        {"type": "code_execution_20250825", "name": "code_execution"},
        # Custom search tool
        SEARCH_CONTRACTS_TOOL,
    ]

    # Step 5: Call Claude with tool use loop
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    # Store search results we send, keyed by source for citation lookup
    sent_search_results: dict[str, dict] = {}
    # Track tool uses for frontend visibility
    tool_uses: list[ToolUseEvent] = []

    max_iterations = 10  # Safety limit
    iteration = 0
    answer = ""
    citations = []

    while iteration < max_iterations:
        iteration += 1
        logger.info(f"Claude API call iteration {iteration}")

        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16384,
            system=system_prompt,
            messages=messages,
            tools=tools,
            betas=BETA_HEADERS,
        )

        # Track usage
        if response.usage:
            total_usage["input_tokens"] += response.usage.input_tokens
            total_usage["output_tokens"] += response.usage.output_tokens

        # Log all block types for debugging
        block_types = [getattr(b, "type", "unknown") for b in response.content]
        logger.info(f"Response block types: {block_types}, stop_reason: {response.stop_reason}")

        # Check for server-side tool uses (code_execution) in ANY response
        from datetime import datetime
        for block in response.content:
            if hasattr(block, "type"):
                if block.type == "server_tool_use":
                    tool_name = getattr(block, "name", "unknown")
                    logger.info(f"Found server_tool_use: {tool_name}")
                    if tool_name == "code_execution":
                        tool_uses.append(ToolUseEvent(
                            tool_name="code_execution",
                            input_summary="Analyzing contracts data with Python",
                            output_summary="Running code...",
                            timestamp=datetime.utcnow().isoformat() + "Z",
                        ))
                elif block.type == "code_execution_tool_result":
                    logger.info("Found code_execution_tool_result")
                    content = getattr(block, "content", None)
                    return_code = getattr(content, "return_code", 0) if content else 0
                    # Update the last code_execution tool use with result
                    for tu in reversed(tool_uses):
                        if tu.tool_name == "code_execution" and tu.output_summary == "Running code...":
                            tu.output_summary = "Code executed successfully" if return_code == 0 else f"Code failed (exit {return_code})"
                            break

        # Check stop reason
        if response.stop_reason == "end_turn":
            # Claude is done - extract final answer and citations
            answer, citations = _extract_answer_and_citations(response.content)
            logger.info(f"Chat complete after {iteration} iterations, {len(citations)} citations, {len(tool_uses)} tool_uses")
            break

        elif response.stop_reason == "tool_use":
            # Claude wants to use a tool
            # Add assistant's response to messages
            messages.append({"role": "assistant", "content": response.content})

            # Process each tool use
            tool_results = []
            from datetime import datetime

            for block in response.content:
                if not hasattr(block, "type"):
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"

                # Server-side tool use (code_execution)
                if block.type == "server_tool_use":
                    tool_name = getattr(block, "name", "unknown")
                    logger.info(f"Server tool use: {tool_name}")

                    if tool_name == "code_execution":
                        # Extract code snippet for summary
                        code_input = getattr(block, "input", {})
                        code_snippet = code_input.get("code", "")[:50] if isinstance(code_input, dict) else ""
                        tool_uses.append(ToolUseEvent(
                            tool_name="code_execution",
                            input_summary="Analyzing contracts data with Python",
                            output_summary="Running code...",
                            timestamp=timestamp,
                        ))

                # Code execution result (update the output_summary)
                elif block.type == "code_execution_tool_result":
                    content = getattr(block, "content", {})
                    return_code = content.return_code if hasattr(content, "return_code") else 0
                    # Update the last code_execution tool use with result
                    for tu in reversed(tool_uses):
                        if tu.tool_name == "code_execution" and tu.output_summary == "Running code...":
                            tu.output_summary = "Code executed successfully" if return_code == 0 else f"Code failed (exit {return_code})"
                            break

                # Custom tool use (search_contracts)
                elif block.type == "tool_use":
                    tool_name = block.name
                    tool_id = block.id
                    tool_input = block.input

                    logger.info(f"Tool use: {tool_name}")

                    # Handle our custom tool
                    if tool_name == "search_contracts":
                        query = tool_input.get("query", "")[:100]
                        contract_id = tool_input.get("contract_id")
                        input_summary = f"Search: '{query}'"
                        if contract_id:
                            input_summary += f" in contract {contract_id}"

                        result_content = _handle_tool_use(tool_name, tool_input)

                        # Store search results for citation lookup later
                        num_results = 0
                        for item in result_content:
                            if item.get("type") == "search_result":
                                source = item.get("source", "")
                                sent_search_results[source] = item
                                num_results += 1

                        tool_uses.append(ToolUseEvent(
                            tool_name="search_contracts",
                            input_summary=input_summary,
                            output_summary=f"Found {num_results} matching chunks",
                            timestamp=timestamp,
                        ))

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": result_content,
                            }
                        )

            # If we have tool results to send back, add them
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "pause_turn":
            # Long-running turn paused - continue
            logger.info("Turn paused, continuing...")
            messages.append({"role": "assistant", "content": response.content})
            # Continue the loop to let Claude resume
            continue

        else:
            # Unexpected stop reason
            logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
            answer, citations = _extract_answer_and_citations(response.content)
            break

    else:
        # Hit max iterations
        logger.warning(f"Hit max iterations ({max_iterations})")
        if response:
            answer, citations = _extract_answer_and_citations(response.content)
        else:
            answer = "I encountered an error processing your request."

    # Build sources from citations (only the ones actually used)
    all_sources: list[ContractSource] = []
    for citation in citations:
        source_key = citation.get("source", "")
        if source_key in sent_search_results:
            item = sent_search_results[source_key]
            contract_id = source_key.replace("contract://", "") if source_key.startswith("contract://") else ""
            all_sources.append(
                ContractSource(
                    contract_id=contract_id,
                    filename=item.get("title", ""),
                    text=citation.get("cited_text", "")[:200],  # Use the actual cited text
                    score=0.0,
                )
            )

    # Clean up: delete the uploaded file
    try:
        client.beta.files.delete(file_id, betas=["files-api-2025-04-14"])
        logger.info(f"Deleted temporary file: {file_id}")
    except Exception as e:
        logger.warning(f"Failed to delete file {file_id}: {e}")

    return ChatResult(
        answer=answer,
        sources=all_sources,
        tool_uses=tool_uses,
        usage={
            "input_tokens": total_usage["input_tokens"],
            "output_tokens": total_usage["output_tokens"],
            "total_tokens": total_usage["input_tokens"] + total_usage["output_tokens"],
        },
    )
