"""
CLI batch evaluation: RAG vs vanilla LLM.

Usage:
    python -m rag_app.eval -q rag_app/test_questions.json -o eval_results.json
"""

import argparse
import json
import sys

from rag_app.models.schemas import EvalQuestion
from rag_app.services.eval_service import EvalService
from rag_app.services.rag_pipeline import RAGPipeline


def load_questions(path: str) -> list[EvalQuestion]:
    """Load questions from a JSON file.

    Supports three formats:
      - Full objects: [{"question": "...", "ground_truth": "...", "source_filter": "..."}]
      - Minimal objects: [{"question": "..."}]
      - Bare strings: ["What is ...?", "How does ...?"]
    """
    with open(path) as f:
        data = json.load(f)

    questions = []
    for item in data:
        if isinstance(item, str):
            questions.append(EvalQuestion(question=item))
        elif isinstance(item, dict):
            questions.append(EvalQuestion(**item))
        else:
            print(f"Warning: skipping unrecognized item: {item}")
    return questions


def print_report(results, summary):
    """Print a formatted evaluation report to stdout."""
    print("\n" + "=" * 70)
    print("  RAG EVALUATION REPORT")
    print("=" * 70)

    for i, r in enumerate(results, 1):
        print(f"\n{'─' * 70}")
        print(f"  Q{i}: {r.question}")
        print(f"{'─' * 70}")
        print(f"  RAG avg: {r.rag_eval.average_score:.2f}  |  "
              f"Vanilla avg: {r.vanilla_eval.average_score:.2f}  |  "
              f"RAG advantage: {r.rag_advantage:+.2f}")
        print()
        print(f"  {'Criterion':<25} {'RAG':>5} {'Vanilla':>8}")
        print(f"  {'─' * 40}")

        rag_by_crit = {s.criterion: s for s in r.rag_eval.scores}
        van_by_crit = {s.criterion: s for s in r.vanilla_eval.scores}
        for crit in ["Factual Accuracy", "Obligation Extraction", "Deadline Accuracy",
                      "Hallucination Rate", "Nuance Handling"]:
            rag_s = rag_by_crit.get(crit)
            van_s = van_by_crit.get(crit)
            rag_v = rag_s.score if rag_s else "-"
            van_v = van_s.score if van_s else "-"
            print(f"  {crit:<25} {str(rag_v):>5} {str(van_v):>8}")

    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    print(f"  Questions evaluated: {summary.total_questions}")
    print(f"  RAG overall avg:     {summary.rag_average:.2f}")
    print(f"  Vanilla overall avg: {summary.vanilla_average:.2f}")
    print(f"  RAG advantage:       {summary.rag_advantage:+.2f}")
    print(f"  Wins / Losses / Ties: {summary.wins} / {summary.losses} / {summary.ties}")
    print()
    print(f"  {'Criterion':<25} {'RAG avg':>8} {'Vanilla avg':>12}")
    print(f"  {'─' * 47}")
    for crit in ["Factual Accuracy", "Obligation Extraction", "Deadline Accuracy",
                  "Hallucination Rate", "Nuance Handling"]:
        rag_v = summary.per_criterion_rag.get(crit, 0)
        van_v = summary.per_criterion_vanilla.get(crit, 0)
        print(f"  {crit:<25} {rag_v:>8.2f} {van_v:>12.2f}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Batch RAG evaluation")
    parser.add_argument("-q", "--questions", required=True, help="Path to questions JSON file")
    parser.add_argument("-o", "--output", help="Path to save full JSON results")
    args = parser.parse_args()

    # Load questions
    questions = load_questions(args.questions)
    print(f"Loaded {len(questions)} questions from {args.questions}")

    # Initialize pipeline (same as FastAPI lifespan)
    print("Initializing RAG pipeline...")
    pipeline = RAGPipeline()

    # Check index
    info = pipeline.vector_store.collection_info()
    if not info.get("points_count", 0):
        print("Error: No documents indexed. Run the /index endpoint first.", file=sys.stderr)
        sys.exit(1)

    # Run evaluation
    eval_service = EvalService(pipeline)
    batch_result = eval_service.evaluate_batch(questions)

    # Print report
    print_report(batch_result.results, batch_result.summary)

    # Save JSON if requested
    if args.output:
        with open(args.output, "w") as f:
            f.write(batch_result.model_dump_json(indent=2))
        print(f"\nFull results saved to {args.output}")


if __name__ == "__main__":
    main()
