import json
import re
import tiktoken
from dataclasses import dataclass
from rag_app.config import settings
from rag_app.models.schemas import ChunkMetadata, TextChunk

_encoder = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))


# Negative lookbehind for common abbreviations
_ABBREVIATIONS = r"(?<!Dr)(?<!Mr)(?<!Mrs)(?<!Ms)(?<!No)(?<!Sec)(?<!Govt)(?<!Sr)(?<!Jr)(?<!Ltd)(?<!Inc)(?<!Vol)(?<!Ref)(?<!Art)(?<!Dept)(?<!etc)(?<!viz)(?<!approx)"

_SENTENCE_SPLIT = re.compile(
    _ABBREVIATIONS + r"(?<=[.!?])\s+(?=[A-Z])"
)


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences at sentence boundaries and paragraph breaks."""
    paragraphs = re.split(r"\n\n+", text)
    sentences = []
    for para in paragraphs:
        if not para.strip():
            continue
        parts = _SENTENCE_SPLIT.split(para.strip())
        for i, part in enumerate(parts):
            part = part.strip()
            if part:
                if i == 0 and sentences:
                    sentences.append("\n\n" + part)
                else:
                    sentences.append(part)
    return sentences


def _force_split_by_tokens(text: str, target_tokens: int) -> list[str]:
    """Split text into pieces of ~target_tokens by decoding token spans."""
    tokens = _encoder.encode(text)
    pieces = []
    for i in range(0, len(tokens), target_tokens):
        piece = _encoder.decode(tokens[i : i + target_tokens])
        pieces.append(piece.strip())
    return [p for p in pieces if p]


# ── 2a: Section Splitter ────────────────────────────────────

@dataclass
class RawSection:
    heading: str
    body: str
    level: int       # 1 = top-level, 2 = sub-section
    number: str      # e.g. "3", "II", "(1)", "2.3"


# Patterns ordered from most specific to least specific
_SECTION_PATTERNS = [
    # Sub-section: 2.3, 10.1.2
    (re.compile(r"^(\d+\.\d+[\.\d]*)\s+(.*)"), 2),
    # Numbered: 1. Background, 12. Requirements
    (re.compile(r"^(\d+)\.\s+(\S.*)"), 1),
    # Roman numeral: I. , II. , III. , IV. , etc.
    (re.compile(r"^((?:X{0,3})(?:IX|IV|V?I{0,3}))\.\s+(.*)", re.IGNORECASE), 1),
    # Parenthesized number: (1), (2), (12)
    (re.compile(r"^\((\d+)\)\s+(.*)"), 2),
    # ALL CAPS heading (at least 4 chars, alone on a line)
    (re.compile(r"^([A-Z][A-Z\s]{3,}):?\s*$"), 1),
]


def _split_into_sections(text: str) -> list[RawSection]:
    """Split text into sections using Indian regulatory formatting conventions."""
    lines = text.split("\n")
    sections: list[RawSection] = []
    current_heading = ""
    current_body_lines: list[str] = []
    current_level = 1
    current_number = ""

    def _flush_section():
        body = "\n".join(current_body_lines).strip()
        if current_heading or body:
            sections.append(RawSection(
                heading=current_heading,
                body=body,
                level=current_level,
                number=current_number,
            ))

    for line in lines:
        stripped = line.strip()
        if not stripped:
            current_body_lines.append("")
            continue

        matched = False
        for pattern, level in _SECTION_PATTERNS:
            m = pattern.match(stripped)
            if m:
                # Flush previous section
                _flush_section()
                current_body_lines = []

                groups = m.groups()
                if len(groups) == 2:
                    current_number = groups[0]
                    current_heading = groups[1].strip() if groups[1].strip() else groups[0]
                else:
                    # ALL CAPS heading (single group)
                    current_number = ""
                    current_heading = groups[0].strip()
                current_level = level
                matched = True
                break

        if not matched:
            current_body_lines.append(line)

    # Flush last section
    _flush_section()

    # Fallback: if no section markers found, split by paragraphs
    if len(sections) <= 1 and text.strip():
        return _fallback_paragraph_sections(text)

    return sections


def _fallback_paragraph_sections(text: str) -> list[RawSection]:
    """Fallback: split into paragraph-level sections when no structural markers found."""
    paragraphs = re.split(r"\n\n+", text)
    sections = []
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        # Use first line as heading hint
        first_line = para.split("\n")[0][:80]
        sections.append(RawSection(
            heading=first_line,
            body=para,
            level=1,
            number=str(i),
        ))
    return sections if sections else [RawSection(heading="", body=text, level=1, number="0")]


# ── 2b: Type Classifier ─────────────────────────────────────

_TYPE_RULES: list[tuple[str, list[str], list[str]]] = [
    # (type, heading_keywords, body_patterns)
    ("definition", ["definition", "interpretation"],
     [r'"[^"]+"\s+means', r'"[^"]+"\s+shall mean', r"defined\s+as"]),
    ("applicability", ["applicability", "scope", "application"],
     [r"applicable\s+to", r"applies\s+to", r"shall\s+apply\s+to"]),
    ("exception", ["exception", "exemption", "exclusion"],
     [r"shall\s+not\s+apply", r"notwithstanding", r"except\s+where", r"exempt\s+from"]),
    ("threshold", ["limit", "threshold", "cap", "ratio"],
     [r"Rs\.?\s*[\d,]+", r"\d+\s*%", r"\d+\s*crore", r"\d+\s*lakh"]),
    ("procedure", ["procedure", "process", "filing", "reporting", "manner of"],
     [r"step\s+\d", r"shall\s+(?:file|submit|report|furnish)", r"within\s+\d+\s+days"]),
    ("rule", ["requirement", "obligation", "compliance", "mandate"],
     [r"\bshall\b", r"\bmust\b", r"\bmandatory\b"]),
]


def _classify_section_type(heading: str, body: str) -> str:
    """Rule-based section type classification. First match wins."""
    heading_lower = heading.lower()
    body_lower = body.lower()

    for type_name, heading_keywords, body_patterns in _TYPE_RULES:
        # Check heading keywords
        if any(kw in heading_lower for kw in heading_keywords):
            return type_name

        # Check body patterns — require multiple matches for some types
        match_count = sum(
            1 for pat in body_patterns
            if re.search(pat, body_lower)
        )

        if type_name == "definition" and match_count >= 2:
            return type_name
        elif type_name == "threshold" and match_count >= 2:
            return type_name
        elif type_name == "rule" and match_count >= 2:
            return type_name
        elif type_name in ("applicability", "exception", "procedure") and match_count >= 1:
            return type_name

    return "general"


# ── 2c: Topic Extractor ─────────────────────────────────────

# Pattern to strip leading number prefixes like "3.", "II.", "(1)", "2.3"
_NUMBER_PREFIX = re.compile(
    r"^(?:\d+\.[\d.]*\s*|(?:X{0,3})(?:IX|IV|V?I{0,3})\.\s*|\(\d+\)\s*)",
    re.IGNORECASE,
)


def _extract_topic(heading: str, body: str) -> str:
    """Extract a short topic label from section heading or body."""
    # Try heading first
    if heading:
        topic = _NUMBER_PREFIX.sub("", heading).strip()
        if topic and len(topic) > 2:
            return topic.lower()[:80]

    # Fallback: first sentence of body
    if body:
        first_sentence = _SENTENCE_SPLIT.split(body.strip())[0]
        return first_sentence.strip()[:60].lower()

    return ""


# ── 2d: Section to Chunks ───────────────────────────────────

def _section_to_chunks(
    section: RawSection,
    section_index: int,
    metadata: ChunkMetadata,
    chunk_type: str,
    topic: str,
    target_tokens: int,
    min_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
) -> list[TextChunk]:
    """Convert a single section into one or more TextChunks."""
    # Combine heading + body for full section text
    if section.heading and section.body:
        section_text = f"{section.heading}\n{section.body}"
    elif section.heading:
        section_text = section.heading
    else:
        section_text = section.body

    if not section_text.strip():
        return []

    section_tokens = count_tokens(section_text)

    # Prepare metadata updates
    meta_updates = {
        "chunk_type": chunk_type,
        "topic": topic,
        "section_index": section_index,
        "section_heading": section.heading[:200],
    }

    # Small section → single chunk
    if section_tokens <= max_tokens:
        return [TextChunk(
            chunk_id="",  # assigned later
            text=section_text.strip(),
            token_count=section_tokens,
            metadata=metadata.model_copy(update=meta_updates),
        )]

    # Large section → sub-split using sentence accumulation with intra-section overlap
    sentences = _split_sentences(section_text)
    if not sentences:
        return []

    chunks: list[TextChunk] = []
    current_sentences: list[str] = []
    current_tokens = 0

    def _flush():
        if not current_sentences:
            return
        chunk_text = " ".join(s.strip() for s in current_sentences).strip()
        chunk_text = re.sub(r" +", " ", chunk_text)
        chunk_text = chunk_text.replace(" \n\n ", "\n\n")
        token_count = count_tokens(chunk_text)
        chunks.append(TextChunk(
            chunk_id="",  # assigned later
            text=chunk_text,
            token_count=token_count,
            metadata=metadata.model_copy(update=meta_updates),
        ))

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        if sentence_tokens > max_tokens:
            _flush()
            for sub in _force_split_by_tokens(sentence, target_tokens):
                current_sentences = [sub]
                current_tokens = count_tokens(sub)
                _flush()
            current_sentences = []
            current_tokens = 0
            continue

        if current_tokens + sentence_tokens > max_tokens and current_tokens >= min_tokens:
            _flush()
            # Overlap within section only
            overlap_sents: list[str] = []
            overlap_count = 0
            for s in reversed(current_sentences):
                s_tokens = count_tokens(s)
                if overlap_count + s_tokens > overlap_tokens:
                    break
                overlap_sents.insert(0, s)
                overlap_count += s_tokens
            current_sentences = overlap_sents
            current_tokens = overlap_count

        current_sentences.append(sentence)
        current_tokens += sentence_tokens

    _flush()
    return chunks


# ── 2e: Refactored chunk_document ───────────────────────────

_MIN_SECTION_TOKENS = 50


def chunk_document(
    text: str,
    metadata: ChunkMetadata,
    target_tokens: int = settings.CHUNK_TARGET_TOKENS,
    min_tokens: int = settings.CHUNK_MIN_TOKENS,
    max_tokens: int = settings.CHUNK_MAX_TOKENS,
    overlap_tokens: int = settings.CHUNK_OVERLAP_TOKENS,
) -> list[TextChunk]:
    """Split document text into semantic regulatory-unit chunks."""
    if not text or not text.strip():
        return []

    # Stage 1: Split into sections
    sections = _split_into_sections(text)

    # Merge very short sections with the preceding one
    merged_sections: list[RawSection] = []
    for section in sections:
        full_text = f"{section.heading}\n{section.body}" if section.heading else section.body
        tokens = count_tokens(full_text) if full_text.strip() else 0
        if tokens < _MIN_SECTION_TOKENS and merged_sections:
            # Merge into previous section's body
            prev = merged_sections[-1]
            prev.body = (prev.body + "\n\n" + full_text).strip()
        else:
            merged_sections.append(section)

    # Stage 2 & 3: Classify + extract topic for each section, then convert to chunks
    all_chunks: list[TextChunk] = []
    for section_idx, section in enumerate(merged_sections):
        chunk_type = _classify_section_type(section.heading, section.body)
        topic = _extract_topic(section.heading, section.body)

        section_chunks = _section_to_chunks(
            section=section,
            section_index=section_idx,
            metadata=metadata,
            chunk_type=chunk_type,
            topic=topic,
            target_tokens=target_tokens,
            min_tokens=min_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        all_chunks.extend(section_chunks)

    # Assign sequential chunk_index and chunk_id across all chunks
    total = len(all_chunks)
    for idx, chunk in enumerate(all_chunks):
        chunk.metadata.chunk_index = idx
        chunk.metadata.total_chunks = total
        chunk.chunk_id = f"{metadata.file_name}:{metadata.title[:50]}:chunk_{idx}"

    return all_chunks


# ── 2f: Slimmed classify_chunks ─────────────────────────────

_VALID_CHUNK_TYPES = {"rule", "exception", "definition", "threshold", "applicability", "procedure", "general"}

_CLASSIFY_SYSTEM = (
    "You classify regulatory document chunks into exactly one category.\n"
    "Categories: rule, exception, definition, threshold, applicability, procedure, general\n"
    "- rule: mandatory obligations, directives, compliance requirements\n"
    "- exception: exemptions, carve-outs, exceptions to rules\n"
    "- definition: definitions of terms, acronyms, interpretations\n"
    "- threshold: numerical limits, percentages, monetary limits, ratios\n"
    "- applicability: who/what the regulation applies to, scope\n"
    "- procedure: processes, filings, reporting steps, how-to sequences\n"
    "- general: everything else (introductions, references, misc)\n\n"
    "Input: JSON array of {id, preview}. Output: JSON array of {id, type}.\n"
    "Output ONLY valid JSON, no markdown fences."
)


def classify_chunks(chunks: list[TextChunk], llm) -> list[TextChunk]:
    """LLM-classify only chunks still typed 'general' after rule-based pass.
    If 3 or fewer unclassified, skip LLM entirely."""
    if not chunks:
        return chunks

    # Collect chunks that are still 'general' (rule-based didn't classify them)
    general_chunks = [(i, c) for i, c in enumerate(chunks) if c.metadata.chunk_type == "general"]

    if len(general_chunks) <= 3:
        return chunks

    # Only LLM-classify the general chunks
    batch_size = 20
    consecutive_failures = 0
    max_consecutive_failures = 5  # Abort classification after 5 consecutive failures
    for batch_start in range(0, len(general_chunks), batch_size):
        batch = general_chunks[batch_start : batch_start + batch_size]
        items = []
        for j, (orig_idx, chunk) in enumerate(batch):
            preview = chunk.text[:300]
            items.append({"id": j, "preview": preview})

        prompt = json.dumps(items)
        try:
            raw = llm.generate(prompt, system=_CLASSIFY_SYSTEM, max_tokens=500, temperature=0)
            if not raw:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    print(f"Chunk classification aborted after {max_consecutive_failures} consecutive empty responses. "
                          f"Remaining chunks keep 'general' type.")
                    break
                continue
            consecutive_failures = 0
            raw = raw.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```\w*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            results = json.loads(raw)
            for entry in results:
                idx = entry.get("id")
                ctype = entry.get("type", "general")
                if idx is not None and 0 <= idx < len(batch):
                    if ctype in _VALID_CHUNK_TYPES:
                        orig_idx = batch[idx][0]
                        chunks[orig_idx].metadata.chunk_type = ctype
        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures >= max_consecutive_failures:
                print(f"Chunk classification aborted after {max_consecutive_failures} consecutive failures: {e}. "
                      f"Remaining chunks keep 'general' type.")
                break
            print(f"Chunk classification batch failed (offset {batch_start}): {e}")

    return chunks
