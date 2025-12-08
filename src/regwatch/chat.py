"""
RAG (Retrieval-Augmented Generation) for regulatory chatbot.

Handles:
1. Query rewriting for follow-up questions
2. Retrieval from Qdrant
3. Answer generation with citations
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langfuse import get_client, observe
from openai import OpenAI
from opentelemetry.instrumentation.openai import OpenAIInstrumentor

from regwatch.embeddings import get_embedder
from regwatch.ingest_config import IngestConfig
from regwatch.qdrant_client import RegwatchQdrant

load_dotenv()

logger = logging.getLogger(__name__)

# Prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Initialize OpenAI instrumentation
_instrumentor = OpenAIInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument()


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
class ChatSource:
    """A source chunk used to generate the answer."""

    doc_id: str
    title: str | None
    text: str
    topic: str | None
    score: float


@dataclass
class ChatResult:
    """Result from the chat function."""

    answer: str
    sources: list[ChatSource]
    rewritten_query: str | None = None
    usage: dict | None = None


# Singleton instances
_openai_client: OpenAI | None = None
_qdrant: RegwatchQdrant | None = None


def _get_openai() -> OpenAI:
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI()
    return _openai_client


def _get_qdrant() -> RegwatchQdrant:
    """Get or create Qdrant client."""
    global _qdrant
    if _qdrant is None:
        config = IngestConfig()
        _qdrant = RegwatchQdrant(config)
    return _qdrant


@observe(name="chat-rewrite-query")
def rewrite_query(query: str, history: list[ChatMessage]) -> str:
    """
    Rewrite a follow-up question to be standalone.

    Args:
        query: The user's follow-up question
        history: Conversation history

    Returns:
        Standalone question suitable for retrieval
    """
    if not history:
        return query

    # Format history for prompt
    history_text = "\n".join(
        f"{msg.role.capitalize()}: {msg.content}" for msg in history
    )

    prompt_template = _load_prompt("chat_rewrite_v1")
    prompt = prompt_template.format(history=history_text, query=query)

    # Update Langfuse trace
    langfuse = get_client()
    langfuse.update_current_trace(
        tags=["regwatch-chat", "rewrite"],
        metadata={"history_length": len(history)},
    )

    client = _get_openai()
    response = client.chat.completions.create(
        model="gpt-5-mini-2025-08-07",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=4096,  # Needs headroom for reasoning tokens
    )

    rewritten = response.choices[0].message.content.strip()
    logger.info(f"Rewrote query: '{query}' -> '{rewritten}'")
    return rewritten


def retrieve_chunks(query: str, top_k: int = 20) -> list[ChatSource]:
    """
    Embed query and retrieve similar chunks from Qdrant.

    Args:
        query: The search query (should be standalone)
        top_k: Number of chunks to retrieve

    Returns:
        List of ChatSource objects with retrieved chunks
    """
    embedder = get_embedder()
    query_embedding = embedder.embed_query(query)

    qdrant = _get_qdrant()
    results = qdrant.search(query_embedding, top_k=top_k)

    return [
        ChatSource(
            doc_id=r["doc_id"] or "unknown",
            title=r.get("title"),
            text=r["text"] or "",
            topic=r.get("topic"),
            score=r["score"],
        )
        for r in results
    ]


@observe(name="chat-generate-answer")
def generate_answer(
    query: str,
    sources: list[ChatSource],
    history: list[ChatMessage] | None = None,
) -> tuple[str, dict]:
    """
    Generate an answer using retrieved context.

    Args:
        query: The user's question (standalone form)
        sources: Retrieved chunks
        history: Optional conversation history for context

    Returns:
        Tuple of (answer text, usage stats)
    """
    # Format context from sources
    context_parts = []
    for i, src in enumerate(sources, 1):
        title_str = f" - {src.title}" if src.title else ""
        context_parts.append(f"[{i}] {src.doc_id}{title_str}\n{src.text}")

    context = "\n\n---\n\n".join(context_parts)

    prompt_template = _load_prompt("chat_generation_v1")
    prompt = prompt_template.format(context=context, query=query)

    # Build messages
    messages = []

    # Add history for context (last 4 turns max)
    if history:
        for msg in history[-4:]:
            messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": prompt})

    # Update Langfuse trace
    langfuse = get_client()
    langfuse.update_current_trace(
        tags=["regwatch-chat", "generation"],
        metadata={"num_sources": len(sources), "context_length": len(context)},
    )

    client = _get_openai()
    response = client.chat.completions.create(
        model="gpt-5-mini-2025-08-07",
        messages=messages,
        max_completion_tokens=16384,  # Needs headroom for reasoning tokens
    )

    answer = response.choices[0].message.content.strip()
    usage = {
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }

    return answer, usage


@observe(name="regwatch-chat")
def chat(
    query: str,
    history: list[ChatMessage] | None = None,
    top_k: int = 20,
) -> ChatResult:
    """
    Main chat function - orchestrates RAG pipeline.

    Args:
        query: User's question
        history: Conversation history (optional)
        top_k: Number of chunks to retrieve

    Returns:
        ChatResult with answer, sources, and metadata
    """
    history = history or []

    # Update Langfuse trace
    langfuse = get_client()
    langfuse.update_current_trace(
        name="regwatch-chat",
        tags=["regwatch-chat"],
        metadata={"query": query, "history_length": len(history)},
    )

    # Step 1: Rewrite query if there's history
    rewritten_query = None
    search_query = query

    if history:
        rewritten_query = rewrite_query(query, history)
        search_query = rewritten_query

    # Step 2: Retrieve relevant chunks
    sources = retrieve_chunks(search_query, top_k=top_k)
    logger.info(f"Retrieved {len(sources)} chunks for query: {search_query[:50]}...")

    # Step 3: Generate answer
    answer, usage = generate_answer(search_query, sources, history)

    return ChatResult(
        answer=answer,
        sources=sources,
        rewritten_query=rewritten_query,
        usage=usage,
    )
