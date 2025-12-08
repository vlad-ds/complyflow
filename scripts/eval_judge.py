#!/usr/bin/env python3
"""
LLM Judge Evaluation

Uses Gemini 2.5 Flash as an impartial judge to score responses from all 3 models
on Correctness and Citation Formatting.

Prerequisites:
    Run generation first: PYTHONPATH=src uv run python scripts/eval_generation.py

Usage:
    PYTHONPATH=src uv run python scripts/eval_judge.py
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm

from prompts import load_prompt

load_dotenv()

# Paths
GENERATION_RESULTS_PATH = Path("output/regwatch/generation_eval.json")
OUTPUT_PATH = Path("output/regwatch/judge_eval.json")
SUMMARY_PATH = Path("output/regwatch/generation_summary.md")

# Load judge prompt from file
JUDGE_PROMPT = load_prompt("eval_judge_v1")


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
            "raw_response": response.choices[0].message.content if response else None,
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


def run_judge_eval() -> None:
    """Run judge evaluation on all generated responses."""
    print("=" * 70)
    print("LLM JUDGE EVALUATION")
    print("Judge: GPT-4o")
    print("=" * 70)

    # Load generation results
    if not GENERATION_RESULTS_PATH.exists():
        print(f"\nError: Generation results not found at {GENERATION_RESULTS_PATH}")
        print("Run generation first: PYTHONPATH=src uv run python scripts/eval_generation.py")
        return

    with open(GENERATION_RESULTS_PATH) as f:
        gen_data = json.load(f)

    results = gen_data["results"]
    print(f"\nLoaded {len(results)} questions with responses from 3 models")

    # Initialize OpenAI judge
    print("\nInitializing GPT-4o judge...")
    judge_client = OpenAI()

    # Run evaluation
    print("\n" + "=" * 70)
    print("EVALUATING RESPONSES")
    print("=" * 70)

    models = ["gpt-5-mini", "gpt-5.1", "command-r-08-2024", "gemini-2.5-flash"]
    evaluations = []

    for item in tqdm(results, desc="Judging responses"):
        question = item["question"]
        ground_truth = item["ground_truth"]
        target_quote = item["target_quote"]

        item_evals = {
            "question": question,
            "ground_truth": ground_truth,
            "evaluations": {},
        }

        for model_name in models:
            response = item["responses"][model_name]
            answer = response.get("answer")

            eval_result = evaluate_with_judge(
                ground_truth=ground_truth,
                target_quote=target_quote,
                answer=answer,
                client=judge_client,
            )

            item_evals["evaluations"][model_name] = eval_result

            # Rate limit
            time.sleep(0.3)

        evaluations.append(item_evals)

    # Calculate aggregate scores
    print("\n" + "=" * 70)
    print("CALCULATING SCORES")
    print("=" * 70)

    aggregate = {model: {"correctness": [], "citation_quality": [], "groundedness": [], "overall": []} for model in models}

    for item in evaluations:
        for model_name, eval_result in item["evaluations"].items():
            if eval_result.get("error") is None:
                aggregate[model_name]["correctness"].append(eval_result["correctness"]["score"])
                aggregate[model_name]["citation_quality"].append(eval_result["citation_quality"]["score"])
                aggregate[model_name]["groundedness"].append(eval_result["groundedness"]["score"])
                aggregate[model_name]["overall"].append(eval_result["overall_score"])

    # Compute averages
    summary = {}
    for model in models:
        n = len(aggregate[model]["correctness"])
        if n > 0:
            summary[model] = {
                "correctness_avg": round(sum(aggregate[model]["correctness"]) / n, 2),
                "citation_quality_avg": round(sum(aggregate[model]["citation_quality"]) / n, 2),
                "groundedness_avg": round(sum(aggregate[model]["groundedness"]) / n, 2),
                "overall_avg": round(sum(aggregate[model]["overall"]) / n, 2),
                "num_evaluated": n,
            }
        else:
            summary[model] = {"error": "No valid evaluations"}

    # Save results
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "judge_model": "gpt-4o",
            "num_questions": len(results),
        },
        "summary": summary,
        "evaluations": evaluations,
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nSaved detailed evaluations to {OUTPUT_PATH}")

    # Create markdown summary
    create_summary_report(summary, gen_data.get("model_summary", {}), evaluations)

    # Print results
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    print(f"\n{'Model':<25} {'Correct':<10} {'Citations':<12} {'Grounded':<12} {'Overall':<10}")
    print("-" * 70)

    for model in models:
        s = summary[model]
        if "error" not in s:
            print(f"{model:<25} {s['correctness_avg']:<10} {s['citation_quality_avg']:<12} {s['groundedness_avg']:<12} {s['overall_avg']:<10}")
        else:
            print(f"{model:<25} ERROR")

    # Winner
    valid_summaries = {m: s for m, s in summary.items() if "error" not in s}
    if valid_summaries:
        winner = max(valid_summaries, key=lambda m: valid_summaries[m]["overall_avg"])
        print(f"\nWINNER: {winner} (overall avg: {summary[winner]['overall_avg']}/5)")

    print(f"\nFull report saved to: {SUMMARY_PATH}")


def create_summary_report(summary: dict, model_summary: dict, evaluations: list) -> None:
    """Create a markdown summary report."""
    models = ["gpt-5-mini", "gpt-5.1", "command-r-08-2024", "gemini-2.5-flash"]

    report = []
    report.append("# LLM Generation Evaluation Report\n")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    report.append("Judge: GPT-4o\n")

    report.append("\n## Summary Scores\n")
    report.append("| Model | Correctness | Citations | Groundedness | Overall |")
    report.append("| --- | --- | --- | --- | --- |")

    for model in models:
        s = summary.get(model, {})
        if "error" not in s:
            report.append(f"| {model} | {s['correctness_avg']}/5 | {s['citation_quality_avg']}/5 | {s['groundedness_avg']}/5 | **{s['overall_avg']}/5** |")
        else:
            report.append(f"| {model} | ERROR | ERROR | ERROR | ERROR |")

    # Winner
    valid_summaries = {m: s for m, s in summary.items() if "error" not in s}
    if valid_summaries:
        winner = max(valid_summaries, key=lambda m: valid_summaries[m]["overall_avg"])
        report.append(f"\n**Winner: {winner}** (Overall: {summary[winner]['overall_avg']}/5)\n")

    report.append("\n## Token Usage & Cost (from Langfuse)\n")
    report.append("| Model | Input Tokens | Output Tokens | Avg Latency | Cost (Langfuse) |")
    report.append("| --- | --- | --- | --- | --- |")

    for model in models:
        stats = model_summary.get(model, {})
        input_tokens = stats.get("input_tokens", 0)
        output_tokens = stats.get("output_tokens", 0)
        avg_latency = stats.get("avg_latency_s", 0)
        cost = stats.get("langfuse_cost_usd", 0)
        report.append(f"| {model} | {input_tokens:,} | {output_tokens:,} | {avg_latency}s | ${cost:.4f} |")

    report.append("\n## Evaluation Criteria\n")
    report.append("- **Correctness (1-5)**: Does the answer contain key facts from ground truth?")
    report.append("- **Citations (1-5)**: Are claims properly cited with [N] format?")
    report.append("- **Groundedness (1-5)**: Is the answer based solely on provided context?")
    report.append("- **Overall (1-5)**: Composite score assigned by judge\n")

    report.append("\n## Sample Evaluations\n")

    # Show first 3 examples
    for i, item in enumerate(evaluations[:3]):
        report.append(f"\n### Question {i+1}\n")
        report.append(f"**Q:** {item['question']}\n")
        report.append(f"**Ground Truth:** {item['ground_truth'][:200]}...\n")

        for model in models:
            eval_result = item["evaluations"].get(model, {})
            if eval_result and "error" not in eval_result:
                report.append(f"\n**{model}:**")
                report.append(f"- Correctness: {eval_result['correctness']['score']}/5 - {eval_result['correctness']['reason']}")
                report.append(f"- Citations: {eval_result['citation_quality']['score']}/5 - {eval_result['citation_quality']['reason']}")
                report.append(f"- Verdict: {eval_result['verdict']}")

    report.append("\n---\n")
    report.append("*Report generated by eval_judge.py*\n")

    with open(SUMMARY_PATH, "w") as f:
        f.write("\n".join(report))


if __name__ == "__main__":
    run_judge_eval()
