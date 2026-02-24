"""
CLI batch evaluation: RAG vs vanilla LLM.

Usage:
    python -m rag_app.eval -q rag_app/test_questions.json -o eval_results.json
    python -m rag_app.eval -q rag_app/test_questions.json --baselines gpt
"""

import argparse
import json
import sys

from rag_app.models.schemas import EvalQuestion
from rag_app.services.eval_service import EvalService
from rag_app.services.rag_pipeline import RAGPipeline

CRITERIA = [
    "Factual Accuracy", "Obligation Extraction", "Deadline Accuracy",
    "Hallucination Rate", "Nuance Handling",
]


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
    # Detect which baselines were evaluated
    has_gpt = any(r.vanilla_gpt_eval is not None for r in results)
    has_gemini = any(r.vanilla_gemini_eval is not None for r in results)

    baselines_label = "RAG"
    if has_gpt:
        baselines_label += " vs GPT"
    if has_gemini:
        baselines_label += " vs Gemini"

    print("\n" + "=" * 80)
    print(f"  RAG EVALUATION REPORT  ({baselines_label})")
    print("=" * 80)

    for i, r in enumerate(results, 1):
        print(f"\n{'─' * 80}")
        print(f"  Q{i}: {r.question}")
        print(f"{'─' * 80}")

        parts = [f"RAG: {r.rag_eval.average_score:.2f}"]
        if r.vanilla_gpt_eval:
            parts.append(f"GPT: {r.vanilla_gpt_eval.average_score:.2f}")
        if r.vanilla_gemini_eval:
            parts.append(f"Gemini: {r.vanilla_gemini_eval.average_score:.2f}")
        if r.rag_advantage_vs_gpt is not None:
            parts.append(f"RAG vs GPT: {r.rag_advantage_vs_gpt:+.2f}")
        if r.rag_advantage_vs_gemini is not None:
            parts.append(f"RAG vs Gemini: {r.rag_advantage_vs_gemini:+.2f}")
        print(f"  {'  |  '.join(parts)}")
        print()

        # Build header
        header = f"  {'Criterion':<25} {'RAG':>5}"
        if has_gpt:
            header += f" {'GPT':>6}"
        if has_gemini:
            header += f" {'Gemini':>8}"
        print(header)
        print(f"  {'─' * (25 + 6 + (7 if has_gpt else 0) + (9 if has_gemini else 0))}")

        rag_by_crit = {s.criterion: s for s in r.rag_eval.scores}
        gpt_by_crit = {s.criterion: s for s in r.vanilla_gpt_eval.scores} if r.vanilla_gpt_eval else {}
        gem_by_crit = {s.criterion: s for s in r.vanilla_gemini_eval.scores} if r.vanilla_gemini_eval else {}
        for crit in CRITERIA:
            rag_v = str(rag_by_crit[crit].score) if crit in rag_by_crit else "-"
            line = f"  {crit:<25} {rag_v:>5}"
            if has_gpt:
                gpt_v = str(gpt_by_crit[crit].score) if crit in gpt_by_crit else "-"
                line += f" {gpt_v:>6}"
            if has_gemini:
                gem_v = str(gem_by_crit[crit].score) if crit in gem_by_crit else "-"
                line += f" {gem_v:>8}"
            print(line)

    print(f"\n{'=' * 80}")
    print("  SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Questions evaluated:     {summary.total_questions}")
    print(f"  RAG overall avg:         {summary.rag_average:.2f}")
    if summary.vanilla_gpt_average is not None:
        print(f"  Vanilla GPT avg:         {summary.vanilla_gpt_average:.2f}")
    if summary.vanilla_gemini_average is not None:
        print(f"  Vanilla Gemini avg:      {summary.vanilla_gemini_average:.2f}")
    if summary.rag_advantage_vs_gpt is not None:
        print(f"  RAG advantage vs GPT:    {summary.rag_advantage_vs_gpt:+.2f}")
    if summary.rag_advantage_vs_gemini is not None:
        print(f"  RAG advantage vs Gemini: {summary.rag_advantage_vs_gemini:+.2f}")
    print()
    if summary.wins_vs_gpt is not None:
        print(f"  vs GPT    — Wins / Losses / Ties: "
              f"{summary.wins_vs_gpt} / {summary.losses_vs_gpt} / {summary.ties_vs_gpt}")
    if summary.wins_vs_gemini is not None:
        print(f"  vs Gemini — Wins / Losses / Ties: "
              f"{summary.wins_vs_gemini} / {summary.losses_vs_gemini} / {summary.ties_vs_gemini}")
    print()

    header = f"  {'Criterion':<25} {'RAG':>6}"
    if has_gpt:
        header += f" {'GPT':>6}"
    if has_gemini:
        header += f" {'Gemini':>8}"
    print(header)
    print(f"  {'─' * (25 + 7 + (7 if has_gpt else 0) + (9 if has_gemini else 0))}")
    for crit in CRITERIA:
        rag_v = summary.per_criterion_rag.get(crit, 0)
        line = f"  {crit:<25} {rag_v:>6.2f}"
        if has_gpt and summary.per_criterion_vanilla_gpt:
            line += f" {summary.per_criterion_vanilla_gpt.get(crit, 0):>6.2f}"
        if has_gemini and summary.per_criterion_vanilla_gemini:
            line += f" {summary.per_criterion_vanilla_gemini.get(crit, 0):>8.2f}"
        print(line)
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Batch RAG evaluation")
    parser.add_argument("-q", "--questions", required=True, help="Path to questions JSON file")
    parser.add_argument("-o", "--output", help="Path to save full JSON results")
    parser.add_argument(
        "--baselines",
        nargs="+",
        default=["gpt", "gemini"],
        choices=["gpt", "gemini"],
        help="Baselines to evaluate against (default: gpt gemini)",
    )
    args = parser.parse_args()

    # Load questions
    questions = load_questions(args.questions)
    print(f"Loaded {len(questions)} questions from {args.questions}")
    print(f"Baselines: {', '.join(args.baselines)}")

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
    batch_result = eval_service.evaluate_batch(questions, baselines=args.baselines)

    # Print report
    print_report(batch_result.results, batch_result.summary)

    # Save JSON if requested
    if args.output:
        with open(args.output, "w") as f:
            f.write(batch_result.model_dump_json(indent=2))
        print(f"\nFull results saved to {args.output}")


if __name__ == "__main__":
    main()
