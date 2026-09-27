"""Diagnose retrieval failure modes to guide contextualized embedding strategy.

Tests 4 failure categories:
  A) Source confusion — wrong-source chunks polluting results
  B) Section-in-isolation — chunks lack parent document context
  C) Amendment blindness — stale/superseded circulars ranking equally
  D) General recall — overall relevance quality

Run:
    python scripts/diagnose_retrieval.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_app.services.embedding import EmbeddingService
from rag_app.services.vector_store import VectorStore

embedding = EmbeddingService()
vs = VectorStore()

# ── Test Cases ──────────────────────────────────────────────────

# Each test has: query, expected behavior, and a checker function

TEST_CASES = {
    "A_source_confusion": {
        "description": "Do source-specific queries retrieve chunks from the WRONG regulator?",
        "queries": [
            {"q": "SEBI insider trading regulations and penalties", "expected_source": "sebi"},
            {"q": "RBI master direction on KYC for banks", "expected_source": "rbi"},
            {"q": "IRDAI guidelines on health insurance claim settlement", "expected_source": "irdai"},
            {"q": "GST input tax credit rules under section 16", "expected_source": ["cbic", "gst_council", "legislation"]},
            {"q": "SEBI LODR compliance requirements for listed entities", "expected_source": "sebi"},
            {"q": "RBI guidelines on NBFC asset classification and NPA norms", "expected_source": "rbi"},
            {"q": "IRDAI solvency margin requirements for life insurers", "expected_source": "irdai"},
            {"q": "CBIC circular on e-way bill compliance", "expected_source": ["cbic", "gst_council"]},
        ],
    },
    "B_section_in_isolation": {
        "description": "Do contextual queries fail because chunks lost their parent document context?",
        "queries": [
            # These queries need context about WHAT the limit/rule applies to
            {"q": "what is the investment limit for NBFCs in real estate", "check": "context"},
            {"q": "what is the penalty for late filing under GST", "check": "context"},
            {"q": "who is exempt from the SEBI takeover code", "check": "context"},
            {"q": "what are the capital adequacy requirements for small finance banks", "check": "context"},
            {"q": "what is the time limit for claim settlement by health insurers", "check": "context"},
            {"q": "what percentage of net demand and time liabilities must be maintained as CRR", "check": "context"},
        ],
    },
    "C_amendment_blindness": {
        "description": "Do queries about 'current' or 'latest' rules retrieve stale circulars?",
        "queries": [
            {"q": "current RBI master direction on KYC", "check": "recency"},
            {"q": "latest SEBI circular on mutual fund regulations", "check": "recency"},
            {"q": "what are the current GST rates as per the latest council meeting", "check": "recency"},
            {"q": "latest IRDAI guidelines on cyber security", "check": "recency"},
            {"q": "most recent RBI circular on digital lending", "check": "recency"},
            {"q": "updated SEBI regulations on stock broker compliance", "check": "recency"},
        ],
    },
    "D_general_recall": {
        "description": "Overall — are the top results actually relevant to the query?",
        "queries": [
            {"q": "what is the definition of related party transactions under SEBI LODR", "check": "relevance"},
            {"q": "how to file GST annual return GSTR-9", "check": "relevance"},
            {"q": "RBI guidelines on gold loan LTV ratio", "check": "relevance"},
            {"q": "IRDAI requirements for insurance agent licensing", "check": "relevance"},
            {"q": "SEBI regulations on preferential allotment of shares", "check": "relevance"},
            {"q": "reverse charge mechanism under GST for goods transport agency", "check": "relevance"},
        ],
    },
}

TOP_K = 10


def run_diagnostics():
    results = {}

    for category, config in TEST_CASES.items():
        print(f"\n{'='*70}")
        print(f"  {category}: {config['description']}")
        print(f"{'='*70}")

        category_results = []

        for tc in config["queries"]:
            query = tc["q"]
            print(f"\n  Query: {query}")

            # Embed and search
            query_vec = embedding.embed_single(query)
            hits = vs.search(query_vector=query_vec, top_k=TOP_K, score_threshold=0.0)

            if not hits:
                print("    No results!")
                category_results.append({"query": query, "hits": 0, "issues": ["no_results"]})
                continue

            result = {
                "query": query,
                "hits": len(hits),
                "top_score": hits[0]["score"],
                "avg_score": sum(h["score"] for h in hits) / len(hits),
                "issues": [],
            }

            # ── Category A: Source confusion ──
            if "expected_source" in tc:
                expected = tc["expected_source"]
                if isinstance(expected, str):
                    expected = [expected]
                source_counts = {}
                for h in hits:
                    src = h["metadata"].get("source", "unknown")
                    source_counts[src] = source_counts.get(src, 0) + 1

                correct_count = sum(source_counts.get(s, 0) for s in expected)
                wrong_count = len(hits) - correct_count
                result["correct_source_pct"] = round(correct_count / len(hits) * 100, 1)
                result["source_distribution"] = source_counts

                if wrong_count > len(hits) * 0.5:
                    result["issues"].append("severe_source_confusion")
                elif wrong_count > len(hits) * 0.3:
                    result["issues"].append("moderate_source_confusion")

                print(f"    Correct source: {result['correct_source_pct']}% — {source_counts}")

            # ── Category B: Section-in-isolation ──
            if tc.get("check") == "context":
                # Check if top chunks mention the key entity/concept from the query
                # or if they're generic chunks that could apply to anything
                query_keywords = _extract_key_terms(query)
                chunks_with_context = 0
                for h in hits[:5]:  # focus on top 5
                    text_lower = h["text"].lower()
                    title = h["metadata"].get("title", "").lower()
                    source = h["metadata"].get("source", "")
                    # Does the chunk or its title give enough context?
                    keyword_hits = sum(1 for kw in query_keywords if kw in text_lower or kw in title)
                    if keyword_hits >= 2:
                        chunks_with_context += 1

                result["chunks_with_context"] = chunks_with_context
                result["context_score"] = round(chunks_with_context / 5 * 100, 1)

                if chunks_with_context <= 1:
                    result["issues"].append("severe_context_loss")
                elif chunks_with_context <= 2:
                    result["issues"].append("moderate_context_loss")

                print(f"    Context score: {result['context_score']}% ({chunks_with_context}/5 top chunks have query context)")

                # Show what the top chunk actually says
                top = hits[0]
                print(f"    Top hit (score={top['score']:.3f}): [{top['metadata'].get('source')}] {top['metadata'].get('title', '')[:50]}")
                print(f"    Text preview: {top['text'][:120]}...")

            # ── Category C: Amendment blindness ──
            if tc.get("check") == "recency":
                dates = []
                for h in hits[:5]:
                    date = h["metadata"].get("date", "")
                    if date:
                        dates.append(date)

                result["dates_found"] = dates
                if dates:
                    result["newest_date"] = max(dates)
                    result["oldest_date"] = min(dates)
                    # Check date spread
                    years = set()
                    for d in dates:
                        try:
                            years.add(int(d[:4]))
                        except (ValueError, IndexError):
                            pass
                    result["year_spread"] = sorted(years)
                    if len(years) > 1 and min(years) < max(years) - 2:
                        result["issues"].append("stale_results_mixed_in")

                print(f"    Dates in top 5: {dates}")
                if dates:
                    print(f"    Year spread: {sorted(years) if years else 'N/A'}")

            # ── Category D: General recall ──
            if tc.get("check") == "relevance":
                scores = [h["score"] for h in hits[:5]]
                result["top5_scores"] = [round(s, 3) for s in scores]
                result["score_dropoff"] = round(scores[0] - scores[-1], 3) if len(scores) > 1 else 0

                if scores[0] < 0.4:
                    result["issues"].append("low_top_score")
                if result["score_dropoff"] < 0.05:
                    result["issues"].append("flat_scores_no_discrimination")

                print(f"    Top 5 scores: {result['top5_scores']}")
                print(f"    Score dropoff (1st→5th): {result['score_dropoff']}")
                top = hits[0]
                print(f"    Top hit: [{top['metadata'].get('source')}] {top['metadata'].get('title', '')[:60]}")

            category_results.append(result)

        results[category] = category_results

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n\n{'='*70}")
    print("  DIAGNOSIS SUMMARY")
    print(f"{'='*70}\n")

    for category, category_results in results.items():
        all_issues = []
        for r in category_results:
            all_issues.extend(r.get("issues", []))

        total_queries = len(category_results)
        queries_with_issues = sum(1 for r in category_results if r.get("issues"))
        issue_rate = round(queries_with_issues / total_queries * 100, 1) if total_queries else 0

        severity = "LOW" if issue_rate < 25 else "MEDIUM" if issue_rate < 50 else "HIGH"

        # Category-specific summary metric
        metric = ""
        if category == "A_source_confusion":
            avg_correct = sum(r.get("correct_source_pct", 100) for r in category_results) / total_queries
            metric = f"  Avg correct-source rate: {avg_correct:.1f}%"
        elif category == "B_section_in_isolation":
            avg_context = sum(r.get("context_score", 0) for r in category_results) / total_queries
            metric = f"  Avg context score: {avg_context:.1f}%"
        elif category == "C_amendment_blindness":
            stale_count = sum(1 for i in all_issues if "stale" in i)
            metric = f"  Queries with stale results: {stale_count}/{total_queries}"
        elif category == "D_general_recall":
            avg_top = sum(r.get("top5_scores", [0])[0] for r in category_results) / total_queries
            metric = f"  Avg top-1 score: {avg_top:.3f}"

        print(f"  {category}")
        print(f"    Severity: {severity} ({queries_with_issues}/{total_queries} queries had issues)")
        print(f"    Issues: {dict(_count(all_issues)) if all_issues else 'none'}")
        if metric:
            print(metric)
        print()

    # Save raw results
    output_path = os.path.join(os.path.dirname(__file__), "retrieval_diagnosis.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Full results saved to: {output_path}")


def _extract_key_terms(query: str) -> list[str]:
    """Extract important terms from query for context checking."""
    stopwords = {
        "what", "is", "the", "for", "of", "on", "in", "under", "by", "to",
        "are", "a", "an", "how", "do", "does", "who", "which", "that", "this",
        "be", "must", "shall", "should", "can", "may", "will", "as", "per",
        "with", "and", "or", "not", "at", "from", "about", "latest", "current",
        "most", "recent", "updated", "new",
    }
    words = query.lower().split()
    terms = [w.strip("?,.'\"") for w in words if w.strip("?,.'\"") not in stopwords and len(w) > 2]
    return terms


def _count(items):
    """Simple counter."""
    from collections import Counter
    return Counter(items).most_common()


if __name__ == "__main__":
    run_diagnostics()
