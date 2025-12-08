"""
Custom tools for contracts chatbot.

Defines the search_contracts tool for semantic search on contract content.
"""

import logging

from contracts.qdrant_client import ContractsQdrant
from regwatch.embeddings import get_embedder

logger = logging.getLogger(__name__)

# Tool definition with detailed guidance for effective RAG queries
SEARCH_CONTRACTS_TOOL = {
    "name": "search_contracts",
    "description": """Search the full text content of contract documents using semantic search.

PURPOSE:
Use this tool to find specific clauses, terms, provisions, or language within contracts.
The search uses semantic similarity, so phrase your query to match the kind of language
you expect to find in the contract text.

WHEN TO USE:
- Finding specific clauses (termination, renewal, confidentiality, indemnification)
- Locating obligations or requirements mentioned in contracts
- Searching for mentions of specific topics across all contracts
- Quoting exact contract language
- Understanding what a specific contract says about a topic

WHEN NOT TO USE:
- Questions answerable from metadata (use code execution on CSV instead)
- Counting contracts or date calculations
- Filtering by contract type, status, or parties

WRITING EFFECTIVE QUERIES:
1. Use legal/contract terminology that would appear in the actual text
   - Good: "termination for convenience clause"
   - Poor: "how to end the contract early"

2. Be specific about the concept you're looking for
   - Good: "limitation of liability damages cap"
   - Poor: "liability stuff"

3. Include key terms that would appear in the relevant clause
   - Good: "automatic renewal notice period days"
   - Poor: "renewal info"

4. For specific contracts, use contract_id filter to narrow results
   - Combine with a conceptual query about what you're looking for

QUERY EXAMPLES:
- "termination for cause material breach" - finds termination clauses
- "indemnification hold harmless third party claims" - finds indemnity provisions
- "confidential information disclosure restrictions" - finds NDA clauses
- "payment terms net days invoice" - finds payment provisions
- "governing law jurisdiction disputes" - finds choice of law clauses
- "assignment transfer rights consent" - finds assignment restrictions
- "force majeure events beyond control" - finds force majeure clauses
- "intellectual property ownership work product" - finds IP clauses

RESULTS:
Returns up to 20 relevant text excerpts from contracts, ranked by relevance.
Each result includes the contract filename, parties, and the matching text passage.
Citations are automatically enabled for proper source attribution.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Semantic search query using contract/legal terminology. "
                "Phrase it to match language that would appear in contract text. "
                "Include key legal terms relevant to what you're looking for.",
            },
            "contract_id": {
                "type": "string",
                "description": "Optional: Airtable record ID to search within a specific contract only. "
                "Use this when the user asks about a particular contract by name - "
                "you can find the record_id from the CSV data first.",
            },
        },
        "required": ["query"],
    },
}


def handle_search_contracts(
    query: str,
    contract_id: str | None = None,
    top_k: int = 20,
) -> list[dict]:
    """
    Execute semantic search on contracts and return search_result blocks.

    Args:
        query: Search query (should use contract/legal terminology)
        contract_id: Optional filter to search within a specific contract
        top_k: Number of results to return (default 20)

    Returns:
        List of search_result dicts formatted for Claude's search results feature.
        Each dict has: type, source, title, content, citations
    """
    # Embed the query
    embedder = get_embedder()
    query_embedding = embedder.embed_query(query)

    # Search Qdrant
    qdrant = ContractsQdrant()
    results = qdrant.search(
        query_embedding=query_embedding,
        top_k=top_k,
        contract_id=contract_id,
    )

    logger.info(
        f"Search '{query[:50]}...' returned {len(results)} results"
        + (f" (filtered to contract {contract_id})" if contract_id else "")
    )

    # Convert to search_result format for Claude
    search_results = []
    for result in results:
        # Build a descriptive source identifier
        # Format: "Contract: {filename} (ID: {record_id})"
        filename = result.get("filename", "Unknown")
        record_id = result.get("contract_id", "unknown")
        parties = result.get("parties", "")

        # Source is the contract identifier
        source = f"contract://{record_id}"

        # Title includes filename and parties for context
        title_parts = [filename]
        if parties:
            # Parties might be a JSON string or already parsed
            if isinstance(parties, str) and parties.startswith("["):
                try:
                    import json

                    parties_list = json.loads(parties)
                    if parties_list:
                        title_parts.append(f"({', '.join(parties_list[:2])})")
                except json.JSONDecodeError:
                    pass
            elif isinstance(parties, list) and parties:
                title_parts.append(f"({', '.join(parties[:2])})")

        title = " ".join(title_parts)

        # The text content
        text = result.get("text", "")

        search_results.append(
            {
                "type": "search_result",
                "source": source,
                "title": title,
                "content": [{"type": "text", "text": text}],
                "citations": {"enabled": True},
            }
        )

    return search_results


def format_tool_result_for_claude(search_results: list[dict]) -> list[dict]:
    """
    Format search results as tool_result content for Claude.

    The search_result blocks go directly in the tool_result content array.

    Args:
        search_results: List of search_result dicts from handle_search_contracts

    Returns:
        List ready to use as tool_result content
    """
    if not search_results:
        # Return a text block if no results
        return [{"type": "text", "text": "No matching contract content found."}]

    return search_results
