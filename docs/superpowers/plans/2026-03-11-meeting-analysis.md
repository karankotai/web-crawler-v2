# Meeting Analysis Feature Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/analyze/meeting/stream` endpoint that decomposes council press releases into multiple topic-focused analyses with Practitioner Insights.

**Architecture:** Two-pass LLM pipeline. Pass 1 extracts topics as JSON. Pass 2 streams a Dhruva-style analysis per topic. Optional RAG augmentation via `use_rag` flag.

**Tech Stack:** FastAPI (existing), SSE streaming (existing `_sse_event`), Gemini/OpenAI LLM provider (existing), Qdrant vector store (existing, for RAG mode).

**Spec:** `docs/superpowers/specs/2026-03-11-meeting-analysis-design.md`

**Sample outputs (reference for prompt tuning):** `data/sample_analyses/analysis_*_v2.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `rag_app/prompts/meeting_analysis.py` | Topic extraction prompt + per-topic analysis prompt | Create |
| `rag_app/prompts/__init__.py` | Export new prompts | Modify (line 1-3) |
| `rag_app/services/rag_pipeline.py` | `extract_topics()` + `analyze_meeting_stream()` methods | Modify (add after line 854) |
| `rag_app/main.py` | `POST /analyze/meeting/stream` endpoint | Modify (add after line 382) |
| `tests/test_meeting_analysis.py` | Unit tests for topic extraction, marker matching, prompt assembly | Create |

---

## Chunk 1: Prompts

### Task 1: Create the meeting analysis prompts

**Files:**
- Create: `rag_app/prompts/meeting_analysis.py`

- [ ] **Step 1: Write the topic extraction prompt**

```python
# rag_app/prompts/meeting_analysis.py

from rag_app.prompts.ca_analysis import _CRITICAL_RULES, _STYLE_RULES

# ── Pass 1: Topic Extraction ─────────────────────────────────

TOPIC_EXTRACTION_SYSTEM_PROMPT = (
    "You are an expert Indian tax and regulatory analyst. "
    "The user has provided the full text of a government council meeting press release "
    "(e.g., GST Council, RBI policy meeting). "
    "Identify 3-7 distinct topics or themes that warrant separate professional analysis.\n\n"
    "For each topic, provide:\n"
    "- title: a concise, professional title (e.g., 'GST Rate Rationalization — Three-Slab Structure')\n"
    "- summary: 2-3 sentences describing what the topic covers\n"
    "- start_marker: an exact phrase (10-30 words) copied verbatim from the text that marks "
    "where this topic's content begins\n"
    "- end_marker: an exact phrase (10-30 words) copied verbatim from the text that marks "
    "where this topic's content ends\n\n"
    "RULES:\n"
    "1. Output ONLY a JSON array. No markdown fences. No commentary.\n"
    "2. start_marker and end_marker must be EXACT substrings from the provided text.\n"
    "3. Topics should not overlap — each section of the text belongs to at most one topic.\n"
    "4. Aim for 3-7 topics. Do not create topics for boilerplate, signatures, or annexure tables.\n"
    "5. Group related rate changes into a single topic rather than listing each item separately.\n"
)
```

- [ ] **Step 2: Write the per-topic analysis prompt**

Add to the same file:

```python
# ── Pass 2: Per-Topic Analysis ───────────────────────────────

MEETING_ANALYSIS_SECTIONS = (
    "OUTPUT FORMAT — produce the following sections:\n\n"
    "### [Topic Title]\n\n"
    "**Executive Summary**\n"
    "2-3 sentences ONLY. Name the authority, date, core change, and effective date.\n\n"
    "## Current Legal Position\n"
    "ONE paragraph (4-6 sentences). What the law says TODAY on this topic. "
    "Write for a CA audience — assume knowledge of GST fundamentals.\n\n"
    "## Proposed Changes\n"
    "Strictly grounded in the provided text. Group related changes into bullets.\n"
    "Each bullet: **[Label]:** [Change]. Previously [old position].\n"
    "5-8 bullets maximum.\n\n"
    "## Sector-Specific Impacts\n"
    "(Only if applicable to this topic — skip this section entirely otherwise.)\n"
    "2-3 sentences per sector. State the rate change, key consequence, one action needed.\n\n"
    "## Action Items\n"
    "6 items maximum. Numbered, verb-led checklist. One line each. Specific deliverables.\n\n"
    "## Practitioner Insights\n"
    "4-5 bullets maximum. Each bullet: 2-3 sentences.\n"
    "Legal implications, practical steps, related provisions, compliance pitfalls.\n"
    "Tone: measured, actionable. No market predictions.\n"
)

_KNOWLEDGE_OVERRIDES = (
    "\nKNOWLEDGE SCOPE EXCEPTIONS:\n"
    "EXCEPTION for 'Current Legal Position' section: You MAY explain the existing legal "
    "provisions (Act sections, Rules) that the document references, drawing on your knowledge "
    "of Indian tax law. This is necessary to provide the 'before' picture.\n\n"
    "EXCEPTION for 'Practitioner Insights' section: You MAY draw on your knowledge of "
    "Indian tax law, GST provisions, and professional practice to provide actionable insights "
    "beyond what the source document states. Clearly distinguish between what the document "
    "says and what you are adding.\n\n"
    "All other sections must be strictly grounded in the provided text.\n"
)

_WORD_BUDGET = (
    "\nWORD BUDGET: 800-1200 words total. This is a hard constraint. "
    "Be dense and precise — every sentence must earn its place. "
    "Write for CAs, not laypeople.\n"
)

MEETING_ANALYSIS_SYSTEM_PROMPT = (
    "You are a senior Chartered Accountant (CA) and regulatory expert specialising in "
    "Indian government regulatory matters. The user has provided an excerpt from a "
    "council meeting press release on a specific topic. Produce a professional analysis.\n\n"
    + _CRITICAL_RULES
    + "\n"
    + _KNOWLEDGE_OVERRIDES
    + "\n"
    + _STYLE_RULES
    + "\n"
    + _WORD_BUDGET
    + "\n"
    + MEETING_ANALYSIS_SECTIONS
)
```

- [ ] **Step 3: Verify imports work**

Run: `cd /Users/karankotai/dev/gov-circular-crawler && python3 -c "from rag_app.prompts.meeting_analysis import TOPIC_EXTRACTION_SYSTEM_PROMPT, MEETING_ANALYSIS_SYSTEM_PROMPT; print('OK', len(TOPIC_EXTRACTION_SYSTEM_PROMPT), len(MEETING_ANALYSIS_SYSTEM_PROMPT))"`

Expected: `OK <number> <number>` — no import errors.

- [ ] **Step 4: Update `__init__.py` exports**

Modify `rag_app/prompts/__init__.py`:

```python
from rag_app.prompts.ca_analysis import ANALYSIS_SECTIONS, CA_ANALYSIS_SYSTEM_PROMPT
from rag_app.prompts.meeting_analysis import (
    MEETING_ANALYSIS_SYSTEM_PROMPT,
    TOPIC_EXTRACTION_SYSTEM_PROMPT,
)

__all__ = [
    "CA_ANALYSIS_SYSTEM_PROMPT",
    "ANALYSIS_SECTIONS",
    "MEETING_ANALYSIS_SYSTEM_PROMPT",
    "TOPIC_EXTRACTION_SYSTEM_PROMPT",
]
```

- [ ] **Step 5: Commit**

```bash
git add rag_app/prompts/meeting_analysis.py rag_app/prompts/__init__.py
git commit -m "feat: add meeting analysis prompts (topic extraction + per-topic)"
```

---

## Chunk 2: Pipeline Methods

### Task 2: Add topic extraction to RAGPipeline

**Files:**
- Modify: `rag_app/services/rag_pipeline.py` (add after line 854)
- Create: `tests/test_meeting_analysis.py`

- [ ] **Step 1: Write tests for `_extract_excerpt` helper**

```python
# tests/test_meeting_analysis.py
import pytest


def test_extract_excerpt_both_markers_found():
    """Markers found — return substring between them."""
    from rag_app.services.rag_pipeline import RAGPipeline

    text = "AAA start here BBB some content CCC end here DDD"
    result = RAGPipeline._extract_excerpt(text, "start here", "end here")
    assert "start here" in result
    assert "some content" in result
    assert "end here" in result
    assert "AAA" not in result
    assert "DDD" not in result


def test_extract_excerpt_start_not_found():
    """Start marker missing — return full text."""
    from rag_app.services.rag_pipeline import RAGPipeline

    text = "AAA BBB CCC"
    result = RAGPipeline._extract_excerpt(text, "MISSING", "CCC")
    assert result == text


def test_extract_excerpt_end_not_found():
    """End marker missing — return full text."""
    from rag_app.services.rag_pipeline import RAGPipeline

    text = "AAA BBB CCC"
    result = RAGPipeline._extract_excerpt(text, "AAA", "MISSING")
    assert result == text


def test_extract_excerpt_end_before_start():
    """End marker appears before start — return full text."""
    from rag_app.services.rag_pipeline import RAGPipeline

    text = "end here AAA start here BBB"
    result = RAGPipeline._extract_excerpt(text, "start here", "end here")
    assert result == text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/karankotai/dev/gov-circular-crawler && python3 -m pytest tests/test_meeting_analysis.py -v`

Expected: FAIL — `_extract_excerpt` doesn't exist yet.

- [ ] **Step 3: Write tests for `_parse_topics_json` helper**

Add to `tests/test_meeting_analysis.py`:

```python
def test_parse_topics_json_valid():
    """Valid JSON array parses correctly."""
    from rag_app.services.rag_pipeline import RAGPipeline

    raw = '[{"title": "T1", "summary": "S1", "start_marker": "a", "end_marker": "b"}]'
    result = RAGPipeline._parse_topics_json(raw)
    assert len(result) == 1
    assert result[0]["title"] == "T1"


def test_parse_topics_json_with_fences():
    """JSON wrapped in markdown fences still parses."""
    from rag_app.services.rag_pipeline import RAGPipeline

    raw = '```json\n[{"title": "T1", "summary": "S1", "start_marker": "a", "end_marker": "b"}]\n```'
    result = RAGPipeline._parse_topics_json(raw)
    assert len(result) == 1


def test_parse_topics_json_invalid():
    """Invalid JSON returns None."""
    from rag_app.services.rag_pipeline import RAGPipeline

    result = RAGPipeline._parse_topics_json("not json at all")
    assert result is None


def test_parse_topics_json_not_array():
    """JSON object (not array) returns None."""
    from rag_app.services.rag_pipeline import RAGPipeline

    result = RAGPipeline._parse_topics_json('{"title": "T1"}')
    assert result is None
```

- [ ] **Step 4: Implement `_extract_excerpt` and `_parse_topics_json`**

Add to `rag_app/services/rag_pipeline.py` inside the `RAGPipeline` class (after the existing `_merge_results` method, around line 795):

```python
    # ── Meeting analysis helpers ─────────────────────────────

    @staticmethod
    def _extract_excerpt(text: str, start_marker: str, end_marker: str) -> str:
        """Extract text between markers. Falls back to full text if markers not found."""
        start_idx = text.find(start_marker)
        end_idx = text.find(end_marker)
        if start_idx < 0 or end_idx < 0 or end_idx <= start_idx:
            return text
        return text[start_idx : end_idx + len(end_marker)]

    @staticmethod
    def _parse_topics_json(raw: str) -> list[dict] | None:
        """Parse LLM output as a JSON array of topics. Returns None on failure."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and len(parsed) > 0:
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/karankotai/dev/gov-circular-crawler && python3 -m pytest tests/test_meeting_analysis.py -v`

Expected: All 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add rag_app/services/rag_pipeline.py tests/test_meeting_analysis.py
git commit -m "feat: add topic extraction helpers with tests"
```

### Task 3: Add `analyze_meeting_stream` method

**Files:**
- Modify: `rag_app/services/rag_pipeline.py`

- [ ] **Step 1: Add the `_extract_topics` method**

Add to `RAGPipeline` class after the helpers from Task 2:

```python
    def _extract_topics(self, text: str) -> list[dict]:
        """Pass 1: Extract topics from a meeting press release via LLM."""
        from rag_app.prompts.meeting_analysis import TOPIC_EXTRACTION_SYSTEM_PROMPT

        prompt = f"<press_release>\n{text}\n</press_release>"
        raw = self.llm.generate(
            prompt=prompt,
            system=TOPIC_EXTRACTION_SYSTEM_PROMPT,
            max_tokens=2000,
            temperature=0,
        )
        topics = self._parse_topics_json(raw)
        if topics:
            print(f"Extracted {len(topics)} topics")
            return topics

        # Retry once
        print("Topic extraction failed, retrying...")
        raw = self.llm.generate(
            prompt=prompt,
            system=TOPIC_EXTRACTION_SYSTEM_PROMPT,
            max_tokens=2000,
            temperature=0.1,
        )
        topics = self._parse_topics_json(raw)
        if topics:
            print(f"Retry extracted {len(topics)} topics")
            return topics

        # Fallback: single topic covering entire document
        print("Topic extraction failed after retry, using single-topic fallback")
        return [{"title": "Meeting Analysis", "summary": "Full document analysis", "start_marker": "", "end_marker": ""}]
```

- [ ] **Step 2: Add the `analyze_meeting_stream` generator**

Add to `RAGPipeline` class:

```python
    def analyze_meeting_stream(
        self,
        text: str,
        use_rag: bool = False,
        source_filter: list[str] | None = None,
    ):
        """Generator yielding SSE events for multi-topic meeting analysis."""
        from rag_app.prompts.meeting_analysis import MEETING_ANALYSIS_SYSTEM_PROMPT

        # Pass 1: extract topics
        topics = self._extract_topics(text)
        total = len(topics)

        # Emit topics event
        topics_summary = [
            {
                "title": t["title"],
                "summary": t.get("summary", ""),
                "excerpt_length": len(self._extract_excerpt(
                    text, t.get("start_marker", ""), t.get("end_marker", ""),
                )),
            }
            for t in topics
        ]
        yield _sse_event("topics", {"topics": topics_summary})

        # Pass 2: per-topic analysis
        for idx, topic in enumerate(topics):
            yield _sse_event("topic_start", {
                "index": idx,
                "title": topic["title"],
                "total": total,
            })

            try:
                # Extract excerpt
                excerpt = self._extract_excerpt(
                    text,
                    topic.get("start_marker", ""),
                    topic.get("end_marker", ""),
                )

                # Build prompt
                context_parts = [f"<press_release_excerpt>\n{excerpt}\n</press_release_excerpt>"]

                # Optional RAG augmentation
                if use_rag:
                    rag_query = f"{topic['title']} {topic.get('summary', '')}"
                    query_vector = self.embedding_service.embed_single(rag_query)
                    rag_results = self.vector_store.search(
                        query_vector=query_vector,
                        top_k=8,
                        source_filter=source_filter,
                    )
                    if rag_results:
                        rag_context = self._build_context(rag_results)
                        context_parts.append(
                            f"\n<related_circulars>\n{rag_context}\n</related_circulars>"
                        )

                prompt = (
                    "\n".join(context_parts)
                    + f"\n\n<topic_title>{topic['title']}</topic_title>"
                    + f"\n<topic_summary>{topic.get('summary', '')}</topic_summary>"
                )

                # Stream analysis
                for chunk in self.llm.generate_stream(
                    prompt=prompt,
                    system=MEETING_ANALYSIS_SYSTEM_PROMPT,
                    max_tokens=4000,
                    temperature=0,
                ):
                    yield _sse_event("token", chunk)

            except Exception as e:
                print(f"Error generating analysis for topic '{topic['title']}': {e}")
                yield _sse_event("error", {
                    "index": idx,
                    "title": topic["title"],
                    "error_message": str(e),
                })

            yield _sse_event("topic_end", {"index": idx})

        yield _sse_event("done", None)
```

- [ ] **Step 3: Verify import works**

Run: `cd /Users/karankotai/dev/gov-circular-crawler && python3 -c "from rag_app.services.rag_pipeline import RAGPipeline; print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add rag_app/services/rag_pipeline.py
git commit -m "feat: add analyze_meeting_stream two-pass pipeline"
```

---

## Chunk 3: API Endpoint

### Task 4: Add the FastAPI endpoint

**Files:**
- Modify: `rag_app/main.py` (add after line 382, after the existing `/analyze/stream` endpoint)

- [ ] **Step 1: Add the endpoint**

Add after the existing `analyze_stream` endpoint (after line 382 in `main.py`):

```python
@app.post("/analyze/meeting/stream")
async def analyze_meeting_stream(
    file: UploadFile | None = None,
    text: str | None = Form(None),
    use_rag: bool = Form(False),
    source_filter: str | None = Form(None),
):
    """Stream multi-topic analysis of a council meeting press release.

    Decomposes the document into distinct topics and produces a separate
    Dhruva-style analysis for each, including Practitioner Insights.
    """
    meeting_text = None

    if file and file.filename:
        pdf_bytes = await file.read()
        meeting_text = _extract_text_from_pdf(pdf_bytes)
    elif text:
        meeting_text = text.strip()

    if not meeting_text or len(meeting_text) < 50:
        raise HTTPException(
            status_code=400,
            detail="Provide meeting text (>=50 chars) or upload a PDF.",
        )

    # Parse source_filter from comma-separated string to list
    filter_list = None
    if source_filter and use_rag:
        filter_list = [s.strip().lower() for s in source_filter.split(",") if s.strip()]
        for s in filter_list:
            if s not in VALID_SOURCES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid source '{s}' in source_filter. Choose from: {sorted(VALID_SOURCES)}",
                )

    return StreamingResponse(
        pipeline.analyze_meeting_stream(meeting_text, use_rag=use_rag, source_filter=filter_list),
        media_type="text/event-stream",
    )
```

- [ ] **Step 2: Verify server starts**

Run: `cd /Users/karankotai/dev/gov-circular-crawler && timeout 5 python3 -c "from rag_app.main import app; print('App loaded, routes:', [r.path for r in app.routes if hasattr(r, 'path')])" 2>&1 | head -20`

Expected: output includes `/analyze/meeting/stream` in the routes list.

- [ ] **Step 3: Commit**

```bash
git add rag_app/main.py
git commit -m "feat: add /analyze/meeting/stream endpoint"
```

### Task 5: Manual smoke test

- [ ] **Step 1: Run server locally**

Run: `cd /Users/karankotai/dev/gov-circular-crawler && uvicorn rag_app.main:app --port 8000`

(In a separate terminal or use curl.)

- [ ] **Step 2: Test with the GST Council press release**

```bash
curl -X POST http://localhost:8000/analyze/meeting/stream \
  -F "text=$(head -c 15000 /tmp/gst_56_full_source.txt)" \
  2>/dev/null | head -50
```

Expected: SSE events — first a `topics` event with 3-7 topics, then `topic_start`/`token`/`topic_end` cycles.

- [ ] **Step 3: Test with PDF upload**

```bash
curl -X POST http://localhost:8000/analyze/meeting/stream \
  -F "file=@/path/to/press_release.pdf" \
  2>/dev/null | head -20
```

Expected: Same SSE event flow.

- [ ] **Step 4: Test error case (no input)**

```bash
curl -X POST http://localhost:8000/analyze/meeting/stream 2>/dev/null
```

Expected: 400 error with "Provide meeting text" message.

- [ ] **Step 5: Run all tests**

Run: `cd /Users/karankotai/dev/gov-circular-crawler && python3 -m pytest tests/ -v`

Expected: All tests pass (existing + new).

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: meeting analysis — complete implementation with tests"
```
