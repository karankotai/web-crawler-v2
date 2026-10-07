#!/usr/bin/env python3
"""Evaluate RAG system on 20 advanced regulatory questions.

Loads questions + ground truth from data/advanced_test_questions.json,
calls the /evaluate endpoint for each, and saves scored results.

Usage:
    python scripts/eval_advanced_20q.py                    # Full eval (RAG only)
    python scripts/eval_advanced_20q.py --baselines gpt    # Also compare vs vanilla GPT
    python scripts/eval_advanced_20q.py --quick             # Skip baselines, RAG only
    python scripts/eval_advanced_20q.py --questions 4 12 13 # Evaluate specific questions only
"""

import argparse
import json
import os
import sys
import time

import requests

API_BASE = os.environ.get("RAG_API_URL", "http://localhost:8000")
QUESTIONS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "data", "advanced_test_questions.json")
RESULTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "advanced_test_results.json")


def load_questions(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def evaluate_question(q: dict, baselines: list[str]) -> dict:
    """Call /evaluate endpoint for a single question."""
    payload = {
        "question": q["question"],
        "ground_truth": q["ground_truth"],
        "source_filter": q.get("source_filter"),
        "baselines": baselines,
    }
    resp = requests.post(f"{API_BASE}/evaluate", json=payload, timeout=180)
    resp.raise_for_status()
    return resp.json()["result"]


def print_summary(results: list[dict]):
    """Print a concise summary of evaluation results."""
    print("\n" + "=" * 80)
    print("EVALUATION SUMMARY")
    print("=" * 80)

    rag_scores = []
    weak_questions = []

    for i, r in enumerate(results, 1):
        rag = r.get("rag_eval", {})
        avg = rag.get("average_score", 0)
        total = rag.get("total_score", 0)
        rag_scores.append(avg)

        # Per-criterion breakdown
        criteria = {s["criterion"]: s["score"] for s in rag.get("scores", [])}
        fa = criteria.get("Factual Accuracy", 0)
        oe = criteria.get("Obligation Extraction", 0)
        da = criteria.get("Deadline Accuracy", 0)
        hr = criteria.get("Hallucination Rate", 0)
        nh = criteria.get("Nuance Handling", 0)

        status = "OK" if avg >= 4.0 else "WEAK" if avg >= 3.0 else "FAIL"
        marker = " ***" if avg < 4.0 else ""
        print(f"  Q{i:2d}: avg={avg:.1f} total={total:2d} "
              f"[FA={fa} OE={oe} DA={da} HR={hr} NH={nh}] {status}{marker}")

        if avg < 4.0:
            weak_questions.append((i, avg, r["question"][:60]))

    overall = sum(rag_scores) / len(rag_scores) if rag_scores else 0
    print(f"\n  OVERALL RAG AVERAGE: {overall:.2f} / 5.00")
    print(f"  Questions >= 4.0: {sum(1 for s in rag_scores if s >= 4.0)}/{len(rag_scores)}")
    print(f"  Questions >= 4.5: {sum(1 for s in rag_scores if s >= 4.5)}/{len(rag_scores)}")

    if weak_questions:
        print(f"\n  WEAK QUESTIONS (< 4.0):")
        for qnum, avg, text in weak_questions:
            print(f"    Q{qnum} ({avg:.1f}): {text}...")

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Evaluate RAG on 20 advanced questions")
    parser.add_argument("--baselines", nargs="*", default=[],
                        help="Baseline models to compare (gpt, gemini)")
    parser.add_argument("--quick", action="store_true",
                        help="Skip baselines, RAG evaluation only")
    parser.add_argument("--questions", nargs="*", type=int,
                        help="Specific question numbers to evaluate (1-indexed)")
    parser.add_argument("--output", default=RESULTS_FILE,
                        help="Output file path")
    args = parser.parse_args()

    # Load questions
    questions = load_questions(QUESTIONS_FILE)
    print(f"Loaded {len(questions)} questions from {QUESTIONS_FILE}")

    # Filter to specific questions if requested
    if args.questions:
        indices = [q - 1 for q in args.questions if 1 <= q <= len(questions)]
        questions_to_eval = [(i, questions[i]) for i in indices]
    else:
        questions_to_eval = list(enumerate(questions))

    baselines = [] if args.quick else args.baselines

    # Check server health
    try:
        health = requests.get(f"{API_BASE}/health", timeout=10).json()
        points = health.get("collection", {}).get("points_count", 0)
        print(f"Server healthy: {points} vectors indexed")
    except Exception as e:
        print(f"ERROR: Cannot reach server at {API_BASE}: {e}")
        sys.exit(1)

    # Run evaluation
    results = []
    for idx, q in questions_to_eval:
        qnum = idx + 1
        print(f"\n[{len(results)+1}/{len(questions_to_eval)}] Q{qnum}: {q['question'][:70]}...")
        start = time.time()
        try:
            result = evaluate_question(q, baselines)
            elapsed = time.time() - start
            result["q_num"] = qnum
            results.append(result)
            avg = result.get("rag_eval", {}).get("average_score", 0)
            print(f"  Score: {avg:.1f}/5.0 ({elapsed:.1f}s)")
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"q_num": qnum, "question": q["question"], "error": str(e)})

    # Save results
    with open(args.output, "w") as f:
        json.dump({"results": results}, f, indent=2)
    print(f"\nResults saved to {args.output}")

    # Print summary
    valid_results = [r for r in results if "error" not in r]
    if valid_results:
        print_summary(valid_results)


if __name__ == "__main__":
    main()
