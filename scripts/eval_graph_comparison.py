#!/usr/bin/env python3
"""A/B comparison of RAG answers with and without graph augmentation.

Usage:
    python scripts/eval_graph_comparison.py --mode baseline   # capture vector-only answers
    python scripts/eval_graph_comparison.py --mode graph      # capture graph-augmented answers
    python scripts/eval_graph_comparison.py --mode compare    # side-by-side comparison

Set GRAPH_ENABLED=true in .env before running --mode graph.
"""

import argparse
import json
import os
import sys
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("RAG_BASE_URL", "http://localhost:8000")
QUESTIONS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "graph_eval_questions.json")
BASELINE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "eval_baseline.json")
GRAPH_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "eval_graph_enabled.json")


def load_questions() -> list[dict]:
    with open(QUESTIONS_PATH) as f:
        return json.load(f)


def run_questions(questions: list[dict]) -> list[dict]:
    """Run each question through /ask and collect responses."""
    results = []
    for i, q in enumerate(questions, 1):
        print(f"  [{i}/{len(questions)}] {q['question'][:60]}...")
        try:
            resp = requests.post(
                f"{BASE_URL}/ask",
                json={"question": q["question"], "top_k": 12},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            results.append({
                "category": q["category"],
                "question": q["question"],
                "why_graph_helps": q["why_graph_helps"],
                "answer": data.get("answer", ""),
                "sources": data.get("sources", []),
                "chunks_retrieved": data.get("chunks_retrieved", 0),
                "graph_context": data.get("graph_context"),
                "query_used": data.get("query_used", ""),
            })
        except Exception as e:
            print(f"    ERROR: {e}")
            results.append({
                "category": q["category"],
                "question": q["question"],
                "why_graph_helps": q["why_graph_helps"],
                "answer": f"ERROR: {e}",
                "sources": [],
                "chunks_retrieved": 0,
                "graph_context": None,
                "query_used": "",
            })
    return results


def save_results(results: list[dict], path: str):
    output = {
        "timestamp": datetime.now().isoformat(),
        "total_questions": len(results),
        "results": results,
    }
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved {len(results)} results to {path}")


def compare():
    """Side-by-side comparison of baseline vs graph results."""
    if not os.path.exists(BASELINE_PATH):
        print("ERROR: No baseline results found. Run with --mode baseline first.")
        sys.exit(1)
    if not os.path.exists(GRAPH_PATH):
        print("ERROR: No graph results found. Run with --mode graph first.")
        sys.exit(1)

    with open(BASELINE_PATH) as f:
        baseline = json.load(f)
    with open(GRAPH_PATH) as f:
        graph = json.load(f)

    print(f"\n{'=' * 80}")
    print(f"  COMPARISON: Baseline vs Graph-Augmented RAG")
    print(f"  Baseline: {baseline['timestamp']}")
    print(f"  Graph:    {graph['timestamp']}")
    print(f"{'=' * 80}")

    for b, g in zip(baseline["results"], graph["results"]):
        print(f"\n{'─' * 80}")
        print(f"  Category: {b['category']}")
        print(f"  Question: {b['question']}")
        print(f"  Why graph helps: {b['why_graph_helps']}")
        print(f"{'─' * 80}")

        print(f"\n  BASELINE answer ({b['chunks_retrieved']} chunks):")
        print(f"    {b['answer'][:300]}{'...' if len(b['answer']) > 300 else ''}")

        print(f"\n  GRAPH answer ({g['chunks_retrieved']} chunks):")
        print(f"    {g['answer'][:300]}{'...' if len(g['answer']) > 300 else ''}")

        if g.get("graph_context"):
            gc = g["graph_context"]
            if gc.get("amendment_chain"):
                print(f"\n    Graph chain: {' → '.join(gc['amendment_chain'])}")
            if gc.get("freshness_notes"):
                for cn, note in gc["freshness_notes"].items():
                    print(f"    Freshness: {cn} — {note}")
            if gc.get("impact_entities"):
                print(f"    Impact: {', '.join(gc['impact_entities'])}")

        # Source comparison
        b_sources = {s.get("circular_number", s.get("title", "")) for s in b["sources"]}
        g_sources = {s.get("circular_number", s.get("title", "")) for s in g["sources"]}
        new_sources = g_sources - b_sources
        dropped_sources = b_sources - g_sources
        if new_sources:
            print(f"\n    New sources in graph: {new_sources}")
        if dropped_sources:
            print(f"    Dropped sources: {dropped_sources}")

    print(f"\n{'=' * 80}")
    print("  Comparison complete.")


def main():
    parser = argparse.ArgumentParser(description="A/B comparison for graph-augmented RAG")
    parser.add_argument("--mode", choices=["baseline", "graph", "compare"], required=True)
    args = parser.parse_args()

    if args.mode == "compare":
        compare()
        return

    questions = load_questions()
    print(f"Loaded {len(questions)} test questions")

    if args.mode == "baseline":
        print(f"\nRunning BASELINE (vector-only) — ensure GRAPH_ENABLED=false")
        results = run_questions(questions)
        save_results(results, BASELINE_PATH)
    elif args.mode == "graph":
        print(f"\nRunning GRAPH-AUGMENTED — ensure GRAPH_ENABLED=true")
        results = run_questions(questions)
        save_results(results, GRAPH_PATH)


if __name__ == "__main__":
    main()
