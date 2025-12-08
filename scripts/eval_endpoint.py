#!/usr/bin/env python3
"""
Endpoint Evaluation for Regwatch Chat

Tests the production /regwatch/chat endpoint against the golden dataset
and runs LLM-as-judge evaluation.

Usage:
    PYTHONPATH=src uv run python scripts/eval_endpoint.py

Environment:
    API_KEY - API key for the endpoint (from .env)
    ENDPOINT_URL - Override production URL (default: Railway production)
"""

from dotenv import load_dotenv
load_dotenv()

import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
from openai import OpenAI
from tqdm import tqdm

from prompts import load_prompt

# Paths
GOLDEN_DATASET_PATH = Path("output/regwatch/golden_dataset.json")
OUTPUT_PATH = Path("output/regwatch/endpoint_eval.json")
JUDGE_OUTPUT_PATH = Path("output/regwatch/endpoint_judge_eval.json")

# Endpoint configuration
PRODUCTION_URL = "https://complyflow-production.up.railway.app/regwatch/chat"
ENDPOINT_URL = os.getenv("ENDPOINT_URL", PRODUCTION_URL)
API_KEY = os.getenv("API_KEY")

# Load judge prompt from file (same as eval_judge.py)
JUDGE_PROMPT = load_prompt("eval_judge_v1")


def call_endpoint(query: str, history: list = None) -> dict:
    """Call the chat endpoint and return the response."""
    start = time.time()

    payload = {"query": query}
    if history:
        payload["history"] = history

    headers = {
        "Content-Type": "application/json",
    }
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    try:
        response = requests.post(
            ENDPOINT_URL,
            json=payload,
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()

        return {
            "answer": result.get("answer"),
            "sources": result.get("sources", []),
            "rewritten_query": result.get("rewritten_query"),
            "usage": result.get("usage", {}),
            "latency_s": round(time.time() - start, 2),
            "error": None,
        }
    except Exception as e:
        return {
            "answer": None,
            "sources": [],
            "rewritten_query": None,
            "usage": {},
            "latency_s": round(time.time() - start, 2),
            "error": str(e),
        }


def evaluate_with_judge(
    ground_truth: str,
    target_quote: str,
    answer: str,
    client: OpenAI,
) -> dict:
    """Evaluate a single answer using GPT-4o as judge."""
    if not answer:
        return {
            "correctness": {"score": 1, "reason": "No answer provided"},
            "citation_quality": {"score": 1, "reason": "No answer provided"},
            "groundedness": {"score": 1, "reason": "No answer provided"},
            "overall_score": 1.0,
            "verdict": "Model failed to generate an answer",
            "error": None,
        }

    prompt = JUDGE_PROMPT.format(
        ground_truth=ground_truth,
        target_quote=target_quote,
        answer=answer,
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert evaluator. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=512,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        result["error"] = None
        return result

    except json.JSONDecodeError as e:
        return {
            "correctness": {"score": 0, "reason": "Failed to parse judge response"},
            "citation_quality": {"score": 0, "reason": "Failed to parse judge response"},
            "groundedness": {"score": 0, "reason": "Failed to parse judge response"},
            "overall_score": 0,
            "verdict": f"JSON parse error: {str(e)}",
            "error": str(e),
        }
    except Exception as e:
        return {
            "correctness": {"score": 0, "reason": "Judge API error"},
            "citation_quality": {"score": 0, "reason": "Judge API error"},
            "groundedness": {"score": 0, "reason": "Judge API error"},
            "overall_score": 0,
            "verdict": f"API error: {str(e)}",
            "error": str(e),
        }


def run_endpoint_eval() -> None:
    """Run evaluation against the production endpoint."""
    print("=" * 70)
    print("ENDPOINT EVALUATION")
    print("=" * 70)
    print(f"Endpoint: {ENDPOINT_URL}")
    print(f"API Key: {'set' if API_KEY else 'NOT SET'}")
    print("=" * 70)

    # Load golden dataset
    if not GOLDEN_DATASET_PATH.exists():
        print(f"Error: Golden dataset not found at {GOLDEN_DATASET_PATH}")
        return

    with open(GOLDEN_DATASET_PATH) as f:
        golden_data = json.load(f)

    print(f"\nLoaded {len(golden_data)} test questions")

    # Test connectivity
    print("\nTesting endpoint connectivity...")
    test_response = call_endpoint("What is DORA?")
    if test_response["error"]:
        print(f"ERROR: Cannot connect to endpoint: {test_response['error']}")
        return
    print(f"Connectivity OK (latency: {test_response['latency_s']}s)")

    # Run generation
    print("\n" + "=" * 70)
    print("GENERATING RESPONSES")
    print("=" * 70)

    results = []
    total_latency = 0
    errors = 0

    for item in tqdm(golden_data, desc="Processing questions"):
        question = item["question"]
        ground_truth = item["ground_truth_answer"]
        source_file = item["source_file"]
        target_quote = item["target_quote"]

        response = call_endpoint(question)
        total_latency += response["latency_s"]

        if response["error"]:
            errors += 1

        results.append({
            "question": question,
            "ground_truth": ground_truth,
            "source_file": source_file,
            "target_quote": target_quote,
            "response": response,
        })

        # Brief pause between requests
        time.sleep(0.5)

    # Save generation results
    num_questions = len(golden_data)
    gen_output = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "endpoint": ENDPOINT_URL,
            "num_questions": num_questions,
        },
        "summary": {
            "total_latency_s": round(total_latency, 2),
            "avg_latency_s": round(total_latency / num_questions, 2),
            "errors": errors,
        },
        "results": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(gen_output, f, indent=2)

    print(f"\nSaved generation results to {OUTPUT_PATH}")
    print(f"Total latency: {total_latency:.2f}s")
    print(f"Avg latency: {total_latency / num_questions:.2f}s")
    print(f"Errors: {errors}")

    # Run judge evaluation
    print("\n" + "=" * 70)
    print("RUNNING LLM JUDGE (GPT-4o)")
    print("=" * 70)

    judge_client = OpenAI()
    evaluations = []

    for item in tqdm(results, desc="Judging responses"):
        response = item["response"]
        answer = response.get("answer")

        eval_result = evaluate_with_judge(
            ground_truth=item["ground_truth"],
            target_quote=item["target_quote"],
            answer=answer,
            client=judge_client,
        )

        evaluations.append({
            "question": item["question"],
            "ground_truth": item["ground_truth"],
            "answer": answer,
            "evaluation": eval_result,
        })

        time.sleep(0.3)

    # Calculate aggregate scores
    correctness_scores = []
    citation_scores = []
    groundedness_scores = []
    overall_scores = []

    for e in evaluations:
        eval_result = e["evaluation"]
        if eval_result.get("error") is None:
            correctness_scores.append(eval_result["correctness"]["score"])
            citation_scores.append(eval_result["citation_quality"]["score"])
            groundedness_scores.append(eval_result["groundedness"]["score"])
            overall_scores.append(eval_result["overall_score"])

    n = len(correctness_scores)
    summary = {
        "endpoint": {
            "correctness_avg": round(sum(correctness_scores) / n, 2) if n > 0 else 0,
            "citation_quality_avg": round(sum(citation_scores) / n, 2) if n > 0 else 0,
            "groundedness_avg": round(sum(groundedness_scores) / n, 2) if n > 0 else 0,
            "overall_avg": round(sum(overall_scores) / n, 2) if n > 0 else 0,
            "num_evaluated": n,
        }
    }

    # Save judge results
    judge_output = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "judge_model": "gpt-4o",
            "endpoint": ENDPOINT_URL,
            "num_questions": num_questions,
        },
        "summary": summary,
        "evaluations": evaluations,
    }

    with open(JUDGE_OUTPUT_PATH, "w") as f:
        json.dump(judge_output, f, indent=2)

    print(f"\nSaved judge results to {JUDGE_OUTPUT_PATH}")

    # Print results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    s = summary["endpoint"]
    print(f"\n{'Metric':<20} {'Score':<10}")
    print("-" * 30)
    print(f"{'Correctness':<20} {s['correctness_avg']}/5")
    print(f"{'Citation Quality':<20} {s['citation_quality_avg']}/5")
    print(f"{'Groundedness':<20} {s['groundedness_avg']}/5")
    print(f"{'Overall':<20} {s['overall_avg']}/5")
    print(f"{'Questions Evaluated':<20} {s['num_evaluated']}")

    # Compare with previous results
    print("\n" + "=" * 70)
    print("COMPARISON WITH PREVIOUS EVAL (GPT-5-mini direct)")
    print("=" * 70)

    prev_judge_path = Path("output/regwatch/judge_eval.json")
    if prev_judge_path.exists():
        with open(prev_judge_path) as f:
            prev_data = json.load(f)

        prev = prev_data["summary"].get("gpt-5-mini", {})
        if prev:
            print(f"\n{'Metric':<20} {'Endpoint':<12} {'Direct':<12} {'Delta':<10}")
            print("-" * 55)
            for metric in ["correctness_avg", "citation_quality_avg", "groundedness_avg", "overall_avg"]:
                endpoint_val = s.get(metric, 0)
                direct_val = prev.get(metric, 0)
                delta = endpoint_val - direct_val
                delta_str = f"+{delta:.2f}" if delta >= 0 else f"{delta:.2f}"
                metric_name = metric.replace("_avg", "").replace("_", " ").title()
                print(f"{metric_name:<20} {endpoint_val:<12} {direct_val:<12} {delta_str:<10}")
    else:
        print("\nNo previous evaluation found for comparison")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    run_endpoint_eval()
