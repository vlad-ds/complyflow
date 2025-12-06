#!/usr/bin/env python3
"""
LLM Generation Evaluation with Langfuse Cost Tracking

Runs 4 LLMs (GPT-5-mini, GPT-5.1, Command-R, Gemini 2.5 Flash) on the golden dataset
using retrieved chunks from Qdrant. All calls are traced to Langfuse for cost tracking.

Usage:
    PYTHONPATH=src uv run python scripts/eval_generation.py
"""

# Load .env BEFORE importing langfuse (it reads env vars at import time)
from dotenv import load_dotenv
load_dotenv()

import json
import os
import time
from datetime import datetime
from pathlib import Path

from langfuse import Langfuse
from openai import OpenAI
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from qdrant_client import QdrantClient
from tqdm import tqdm

from regwatch.embeddings import DocumentEmbedder, RetrievalConfig

# Initialize Langfuse instrumentors for automatic tracing
_openai_instrumentor = OpenAIInstrumentor()
if not _openai_instrumentor.is_instrumented_by_opentelemetry:
    _openai_instrumentor.instrument()

# Instrument Google GenAI (new SDK: google.genai)
try:
    from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
    GoogleGenAIInstrumentor().instrument()
except ImportError:
    pass

# Initialize Langfuse client
langfuse = Langfuse()

# Configuration
retrieval_config = RetrievalConfig()
TOP_K = retrieval_config.top_k
COLLECTION_NAME = retrieval_config.collection_name

# Paths
GOLDEN_DATASET_PATH = Path("output/regwatch/golden_dataset.json")
OUTPUT_PATH = Path("output/regwatch/generation_eval.json")

# API clients
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# Langfuse session for this eval run
SESSION_ID = f"regwatch-eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

# System prompt for all models
SYSTEM_PROMPT = """You are a regulatory compliance expert answering questions about EU financial regulations.

CRITICAL INSTRUCTIONS:
1. Answer ONLY using information from the provided document chunks
2. For EVERY claim, include a citation in [N] format referring to the chunk number
3. If the answer is not in the provided chunks, say "I cannot find this information in the provided documents"
4. Be concise and precise - this is for compliance officers who need accurate information
5. Never use information from your training data - ONLY cite the provided chunks

Example format:
"Financial entities must conduct testing at least yearly [3]. The management body bears ultimate responsibility for ICT risk [7]."
"""


def format_chunks_for_prompt(chunks: list[dict]) -> str:
    """Format retrieved chunks with numbered citations."""
    formatted = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source_file", "unknown")
        text = chunk.get("text", "")
        formatted.append(f"[{i}] Source: {source}\n{text}\n")
    return "\n".join(formatted)


def retrieve_chunks(question: str, embedder: DocumentEmbedder, client: QdrantClient) -> list[dict]:
    """Retrieve relevant chunks from Qdrant."""
    query_embedding = embedder.embed_query(question)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=TOP_K,
    )

    return [
        {
            "text": r.payload["text"],
            "source_file": r.payload["source_file"],
            "score": r.score,
        }
        for r in results.points
    ]


def call_gpt5_mini(question: str, context: str, client: OpenAI) -> dict:
    """Call GPT-5-mini with Langfuse tracing (auto-instrumented)."""
    start = time.time()

    try:
        response = client.chat.completions.create(
            model="gpt-5-mini-2025-08-07",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"DOCUMENT CHUNKS:\n{context}\n\nQUESTION: {question}"},
            ],
            # Note: GPT-5-mini only supports temperature=1 (default)
            max_completion_tokens=1024,
        )
        return {
            "answer": response.choices[0].message.content,
            "model": "gpt-5-mini",
            "model_id": "gpt-5-mini-2025-08-07",
            "latency_s": round(time.time() - start, 2),
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "error": None,
        }
    except Exception as e:
        return {
            "answer": None,
            "model": "gpt-5-mini",
            "model_id": "gpt-5-mini-2025-08-07",
            "latency_s": round(time.time() - start, 2),
            "input_tokens": 0,
            "output_tokens": 0,
            "error": str(e),
        }


def call_gpt5(question: str, context: str, client: OpenAI) -> dict:
    """Call GPT-5.1 with Langfuse tracing (auto-instrumented)."""
    start = time.time()

    try:
        response = client.chat.completions.create(
            model="gpt-5.1-2025-11-13",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"DOCUMENT CHUNKS:\n{context}\n\nQUESTION: {question}"},
            ],
            temperature=0,
            max_completion_tokens=1024,
        )
        return {
            "answer": response.choices[0].message.content,
            "model": "gpt-5.1",
            "model_id": "gpt-5.1-2025-11-13",
            "latency_s": round(time.time() - start, 2),
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "error": None,
        }
    except Exception as e:
        return {
            "answer": None,
            "model": "gpt-5.1",
            "model_id": "gpt-5.1-2025-11-13",
            "latency_s": round(time.time() - start, 2),
            "input_tokens": 0,
            "output_tokens": 0,
            "error": str(e),
        }


def call_cohere(question: str, context: str) -> dict:
    """Call Command-R via Langfuse OpenAI wrapper with Cohere compatibility endpoint."""
    start = time.time()

    # Use Langfuse's OpenAI wrapper with Cohere's compatibility endpoint
    from langfuse.openai import openai
    client = openai.OpenAI(
        api_key=os.getenv("COHERE_API_KEY"),
        base_url="https://api.cohere.ai/compatibility/v1"
    )

    try:
        response = client.chat.completions.create(
            model="command-r-08-2024",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"DOCUMENT CHUNKS:\n{context}\n\nQUESTION: {question}"},
            ],
            max_tokens=1024,
        )
        return {
            "answer": response.choices[0].message.content,
            "model": "command-r-08-2024",
            "model_id": "command-r-08-2024",
            "latency_s": round(time.time() - start, 2),
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "error": None,
        }
    except Exception as e:
        return {
            "answer": None,
            "model": "command-r-08-2024",
            "model_id": "command-r-08-2024",
            "latency_s": round(time.time() - start, 2),
            "input_tokens": 0,
            "output_tokens": 0,
            "error": str(e),
        }


def call_gemini(question: str, context: str) -> dict:
    """Call Gemini 2.5 Flash via google.genai SDK (auto-instrumented)."""
    start = time.time()

    from google import genai

    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    try:
        prompt = f"{SYSTEM_PROMPT}\n\nDOCUMENT CHUNKS:\n{context}\n\nQUESTION: {question}"
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0

        return {
            "answer": response.text,
            "model": "gemini-2.5-flash",
            "model_id": "gemini-2.5-flash",
            "latency_s": round(time.time() - start, 2),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "error": None,
        }
    except Exception as e:
        return {
            "answer": None,
            "model": "gemini-2.5-flash",
            "model_id": "gemini-2.5-flash",
            "latency_s": round(time.time() - start, 2),
            "input_tokens": 0,
            "output_tokens": 0,
            "error": str(e),
        }


def get_langfuse_costs(session_id: str) -> dict:
    """Query Langfuse to get actual costs for this session."""
    from langfuse_client import list_traces, get_trace, list_observations

    # Get traces from this session (give Langfuse time to process)
    time.sleep(3)
    langfuse.flush()
    time.sleep(2)

    traces = list_traces(limit=100, session_id=session_id)

    costs_by_model = {}
    for t in traces:
        trace_detail = get_trace(t['id'])
        cost = trace_detail.get('totalCost', 0) or 0

        # Determine model from observations
        obs = list_observations(trace_id=t['id'])
        model = 'unknown'
        for o in obs:
            if o.get('model'):
                model = o.get('model')
                break

        if model not in costs_by_model:
            costs_by_model[model] = 0
        costs_by_model[model] += cost

    return costs_by_model


def run_generation_eval() -> None:
    """Run generation evaluation with all 4 models, traced to Langfuse."""
    print("=" * 70)
    print("LLM GENERATION EVALUATION (Langfuse Traced)")
    print("=" * 70)
    print(f"Models: GPT-5-mini, GPT-5.1, Command-R, Gemini 2.5 Flash")
    print(f"Top-K chunks: {TOP_K}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Langfuse Session: {SESSION_ID}")
    print("=" * 70)

    # Check credentials
    if not QDRANT_URL or not QDRANT_API_KEY:
        print("\nError: QDRANT_URL and QDRANT_API_KEY must be set in .env")
        return

    # Load golden dataset
    if not GOLDEN_DATASET_PATH.exists():
        print(f"Error: Golden dataset not found at {GOLDEN_DATASET_PATH}")
        return

    with open(GOLDEN_DATASET_PATH) as f:
        golden_data = json.load(f)

    print(f"\nLoaded {len(golden_data)} test questions")

    # Initialize clients
    print("\nInitializing clients...")
    embedder = DocumentEmbedder()
    qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    openai_client = OpenAI()

    # Verify Qdrant collection
    collections = [c.name for c in qdrant_client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        print(f"\nError: Collection '{COLLECTION_NAME}' not found")
        return

    collection_info = qdrant_client.get_collection(collection_name=COLLECTION_NAME)
    print(f"Found collection with {collection_info.points_count} indexed chunks")

    # Run evaluation
    print("\n" + "=" * 70)
    print("GENERATING RESPONSES (traced to Langfuse)")
    print("=" * 70)

    results = []
    total_tokens = {
        "gpt-5-mini": {"input": 0, "output": 0},
        "gpt-5.1": {"input": 0, "output": 0},
        "command-r-08-2024": {"input": 0, "output": 0},
        "gemini-2.5-flash": {"input": 0, "output": 0}
    }
    total_latency = {
        "gpt-5-mini": 0,
        "gpt-5.1": 0,
        "command-r-08-2024": 0,
        "gemini-2.5-flash": 0
    }

    for i, item in enumerate(tqdm(golden_data, desc="Processing questions")):
        question = item["question"]
        ground_truth = item["ground_truth_answer"]
        source_file = item["source_file"]
        target_quote = item["target_quote"]

        # Retrieve chunks
        chunks = retrieve_chunks(question, embedder, qdrant_client)
        context = format_chunks_for_prompt(chunks)

        # Call all 4 models
        gpt5_mini_result = call_gpt5_mini(question, context, openai_client)
        gpt5_result = call_gpt5(question, context, openai_client)
        cohere_result = call_cohere(question, context)
        gemini_result = call_gemini(question, context)

        # Track tokens and latency
        for result in [gpt5_mini_result, gpt5_result, cohere_result, gemini_result]:
            model = result["model"]
            total_tokens[model]["input"] += result["input_tokens"]
            total_tokens[model]["output"] += result["output_tokens"]
            total_latency[model] += result["latency_s"]

        # Store result
        results.append({
            "question": question,
            "ground_truth": ground_truth,
            "source_file": source_file,
            "target_quote": target_quote,
            "retrieved_chunks": [{"source_file": c["source_file"], "score": c["score"]} for c in chunks[:5]],
            "responses": {
                "gpt-5-mini": gpt5_mini_result,
                "gpt-5.1": gpt5_result,
                "command-r-08-2024": cohere_result,
                "gemini-2.5-flash": gemini_result,
            },
        })

        # Brief pause to respect rate limits
        time.sleep(0.5)

    # Flush Langfuse to ensure all traces are sent
    print("\nFlushing traces to Langfuse...")
    langfuse.flush()

    # Get costs from Langfuse
    print("Querying Langfuse for costs...")
    langfuse_costs = get_langfuse_costs(SESSION_ID)

    # Check for errors
    errors = {"gpt-5-mini": 0, "gpt-5.1": 0, "command-r-08-2024": 0, "gemini-2.5-flash": 0}
    for r in results:
        for model, resp in r["responses"].items():
            if resp["error"]:
                errors[model] += 1

    # Build comprehensive output
    num_questions = len(golden_data)
    output_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "num_questions": num_questions,
            "top_k": TOP_K,
            "collection": COLLECTION_NAME,
            "langfuse_session": SESSION_ID,
        },
        "model_summary": {
            "gpt-5-mini": {
                "model_id": "gpt-5-mini-2025-08-07",
                "input_tokens": total_tokens["gpt-5-mini"]["input"],
                "output_tokens": total_tokens["gpt-5-mini"]["output"],
                "total_latency_s": round(total_latency["gpt-5-mini"], 2),
                "avg_latency_s": round(total_latency["gpt-5-mini"] / num_questions, 2),
                "errors": errors["gpt-5-mini"],
                "langfuse_cost_usd": langfuse_costs.get("gpt-5-mini-2025-08-07", 0),
            },
            "gpt-5.1": {
                "model_id": "gpt-5.1-2025-11-13",
                "input_tokens": total_tokens["gpt-5.1"]["input"],
                "output_tokens": total_tokens["gpt-5.1"]["output"],
                "total_latency_s": round(total_latency["gpt-5.1"], 2),
                "avg_latency_s": round(total_latency["gpt-5.1"] / num_questions, 2),
                "errors": errors["gpt-5.1"],
                "langfuse_cost_usd": langfuse_costs.get("gpt-5.1-2025-11-13", 0),
            },
            "command-r-08-2024": {
                "model_id": "command-r-08-2024",
                "input_tokens": total_tokens["command-r-08-2024"]["input"],
                "output_tokens": total_tokens["command-r-08-2024"]["output"],
                "total_latency_s": round(total_latency["command-r-08-2024"], 2),
                "avg_latency_s": round(total_latency["command-r-08-2024"] / num_questions, 2),
                "errors": errors["command-r-08-2024"],
                "langfuse_cost_usd": langfuse_costs.get("command-r-08-2024", 0),
            },
            "gemini-2.5-flash": {
                "model_id": "gemini-2.5-flash",
                "input_tokens": total_tokens["gemini-2.5-flash"]["input"],
                "output_tokens": total_tokens["gemini-2.5-flash"]["output"],
                "total_latency_s": round(total_latency["gemini-2.5-flash"], 2),
                "avg_latency_s": round(total_latency["gemini-2.5-flash"] / num_questions, 2),
                "errors": errors["gemini-2.5-flash"],
                "langfuse_cost_usd": langfuse_costs.get("gemini-2.5-flash", 0),
            },
        },
        "results": results,
    }

    # Save results
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nSaved results to {OUTPUT_PATH}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\nProcessed {num_questions} questions with 4 models")
    print(f"\nModel Performance:")
    print(f"{'Model':<25} {'Tokens (in/out)':<20} {'Latency':<12} {'Cost':<12} {'Errors'}")
    print("-" * 80)
    for model, stats in output_data["model_summary"].items():
        tokens = f"{stats['input_tokens']:,}/{stats['output_tokens']:,}"
        latency = f"{stats['avg_latency_s']}s avg"
        cost = f"${stats['langfuse_cost_usd']:.4f}"
        errs = stats['errors']
        print(f"{model:<25} {tokens:<20} {latency:<12} {cost:<12} {errs}")

    print(f"\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print(f"\nLangfuse Session: {SESSION_ID}")
    print(f"\nRun judge evaluation:")
    print(f"  PYTHONPATH=src uv run python scripts/eval_judge.py")


if __name__ == "__main__":
    run_generation_eval()
