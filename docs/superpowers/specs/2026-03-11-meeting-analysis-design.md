# Meeting Analysis Feature — Design Spec

## Overview

A new endpoint (`POST /analyze/meeting/stream`) that takes a council meeting press release (or similar multi-topic government document) and produces multiple separate Dhruva-style deep-dive analyses — one per identified topic. Each analysis includes a "Practitioner Insights" section that goes beyond the source document to provide actionable expert guidance.

## Motivation

CA firms like Dhruva Advisors take a single GST Council press release and produce N focused PDFs, each covering one topic (e.g., rate rationalization, discount law amendments, anti-profiteering). The current `/analyze/stream` endpoint produces a single monolithic 5-section analysis designed for individual circulars. This feature bridges that gap.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Output structure | Multiple separate analyses (one per topic) | Matches Dhruva's model; each analysis is self-contained and shareable |
| RAG augmentation | Optional via `use_rag` flag | Works immediately without indexed content; enriches output when available |
| Expert commentary | "Practitioner Insights" — legal implications + actionable steps | Middle ground: credible and useful without market speculation |
| Architecture | Two-pass LLM pipeline | Clean separation; focused context per topic; enables RAG per topic |

## API Endpoint

### `POST /analyze/meeting/stream`

**Request** (multipart form):
- `file`: single `UploadFile` PDF upload (optional, intentionally singular — one press release at a time)
- `text`: raw text (optional, alternative to file)
- `use_rag`: boolean, default `false`
- `source_filter`: optional comma-separated string (e.g., `"cbic,gst_council"`) — parsed into a list in the endpoint. Only used when `use_rag=true`.

**PDF handling**: uploaded PDF is converted to text via `extract_text_from_pdf()` (same as existing `/analyze/stream`).

**Response**: SSE stream using the existing `_sse_event()` helper (type inside JSON payload `{"type": ..., "data": ...}`). Event types:
- `topics` — emitted once after Pass 1. `{topics: [{title, summary, excerpt_length}]}`
- `topic_start` — before each topic. `{index, title, total}`
- `token` — streamed analysis text
- `topic_end` — end of one topic
- `error` — if a per-topic generation fails. `{index, title, error_message}`
- `done` — all complete

## Pipeline

### Pass 1 — Topic Extraction

Single LLM call with full press release text. `max_tokens=2000`. Returns JSON array:

```json
[
  {
    "title": "GST Rate Rationalization — Three-Slab Structure",
    "summary": "The council proposes streamlining GST into three slabs...",
    "start_marker": "exact phrase from text marking start",
    "end_marker": "exact phrase from text marking end"
  }
]
```

- Target: 3-7 topics per document
- `start_marker`/`end_marker`: exact phrases from the source to delimit relevant excerpts
- **Marker matching algorithm**: exact substring match via `str.find()`, first occurrence of `start_marker` to first occurrence of `end_marker`. If either marker is not found (returns -1), fall back to full press release text for that topic.
- **JSON extraction**: prompt-based (no `response_format` — must work with both Gemini and OpenAI). Strip markdown fences if present (same approach as existing `_expand_queries`). On parse failure: retry once with same prompt, then fall back to single-topic analysis of the entire document.

### Pass 2 — Per-Topic Analysis (streamed)

`max_tokens=4000` per topic. For 7 topics this is 28,000 output tokens — acceptable for a comprehensive analysis feature.

For each topic:
1. Extract relevant excerpt from press release via markers
2. If `use_rag=true`: search vector store with topic title + summary as query, retrieve top 8 chunks filtered to `source_filter` (parsed as `list[str]` from comma-separated form param)
3. Build prompt with excerpt + optional RAG context
4. Stream analysis with `topic_start`/`token`/`topic_end` events

## Prompt Design

### Topic Extraction Prompt

System prompt instructs the LLM to:
- Read the full press release
- Identify distinct topics/themes warranting separate analysis
- Return structured JSON with title, summary, and text markers
- Aim for 3-7 topics

### Per-Topic Analysis Prompt

Imports `_CRITICAL_RULES` and `_STYLE_RULES` from `ca_analysis.py` (NOT `ANALYSIS_SECTIONS` — the meeting analysis has its own 6-section format). Output format per topic:

```
### [Topic Title]

**Executive Summary**
2-3 sentences. Council recommendation, current law, proposed change.

## Current Legal Position
What the law says TODAY. LLM general knowledge IS allowed here to explain
existing law that the press release refers to. Cite specific sections.

## Proposed Changes
Strictly grounded in press release text.
Each bullet: **[Label]:** [Change]. Previously [old position]. Effective [date].

## Sector-Specific Impacts
(Only if applicable — skip entirely otherwise)
Bulleted by sector with specific impact and action needed.

## Action Items
Numbered, verb-led checklist. Specific deliverables.

## Practitioner Insights
Explicitly uses expert knowledge beyond the source document.
- Legal implications and interpretive risks
- Practical steps businesses should take
- References to related provisions, past rulings, notifications
- Potential compliance pitfalls
Tone: measured, actionable. No market predictions or international comparisons.
```

### Knowledge Sandboxing

The per-topic prompt includes `_CRITICAL_RULES` (which contains "NEVER add information from your general knowledge") but then adds explicit overrides for two sections:

- **"Executive Summary" and "Proposed Changes" and "Sector-Specific Impacts" and "Action Items"**: strictly grounded in source text. `_CRITICAL_RULES` apply as-is.
- **"Current Legal Position"**: override paragraph after `_CRITICAL_RULES` states: "EXCEPTION for 'Current Legal Position' section: You MAY explain the existing legal provisions (Act sections, Rules) that the document references, drawing on your knowledge of Indian tax law. This is necessary to provide the 'before' picture that makes the proposed changes meaningful."
- **"Practitioner Insights"**: override paragraph states: "EXCEPTION for 'Practitioner Insights' section: You MAY draw on your knowledge of Indian tax law, GST provisions, and professional practice to provide actionable insights beyond what the source document states. Clearly distinguish between what the document says and what you are adding."

This explicit override approach prevents contradictory instructions — the LLM sees the general rule first, then the scoped exceptions.

## File Changes

| File | Change |
|---|---|
| `rag_app/prompts/meeting_analysis.py` | **New** — topic extraction prompt + per-topic analysis prompt |
| `rag_app/prompts/__init__.py` | Add new exports |
| `rag_app/services/rag_pipeline.py` | Add `analyze_meeting_stream()` method |
| `rag_app/main.py` | Add `POST /analyze/meeting/stream` endpoint |

### Unchanged

- `/analyze/stream` — existing single-circular analysis
- `ca_analysis.py` — existing prompts (reused via import)
- All schemas — endpoint uses `Form()` params like existing `/analyze/stream`

## Streaming Protocol

```
→ SSE: topics {topics: [{title, summary, excerpt_length}, ...]}
→ SSE: topic_start {index: 0, title: "Rate Rationalization", total: 4}
→ SSE: token "### GST Rate Rational..."
→ SSE: token "ization — Three-Slab..."
→ SSE: ...
→ SSE: topic_end {index: 0}
→ SSE: topic_start {index: 1, title: "Post-Sale Discounts", total: 4}
→ SSE: token "### Post-Sale Discount..."
→ SSE: ...
→ SSE: topic_end {index: 1}
→ SSE: ...
→ SSE: done
```

## Error Handling

- If topic extraction returns invalid JSON: retry once, then fall back to single-topic analysis of the entire document
- If marker extraction fails for a topic: use full press release text as excerpt
- If RAG search returns no results: proceed without RAG context (analysis still works from press release + LLM knowledge)
- If any per-topic generation fails: emit error event for that topic, continue with remaining topics
