import json
import re
import tiktoken
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
    # First split on paragraph breaks
    paragraphs = re.split(r"\n\n+", text)
    sentences = []
    for para in paragraphs:
        if not para.strip():
            continue
        # Split paragraph into sentences
        parts = _SENTENCE_SPLIT.split(para.strip())
        for i, part in enumerate(parts):
            part = part.strip()
            if part:
                # Add paragraph break marker back for non-first sentences
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


def chunk_document(
    text: str,
    metadata: ChunkMetadata,
    target_tokens: int = settings.CHUNK_TARGET_TOKENS,
    min_tokens: int = settings.CHUNK_MIN_TOKENS,
    max_tokens: int = settings.CHUNK_MAX_TOKENS,
    overlap_tokens: int = settings.CHUNK_OVERLAP_TOKENS,
) -> list[TextChunk]:
    """Split document text into token-aware chunks respecting sentence boundaries."""
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks = []
    current_sentences: list[str] = []
    current_tokens = 0

    def _flush():
        if not current_sentences:
            return
        chunk_text = " ".join(s.strip() for s in current_sentences).strip()
        # Clean up double spaces from join
        chunk_text = re.sub(r" +", " ", chunk_text)
        # Restore paragraph breaks
        chunk_text = chunk_text.replace(" \n\n ", "\n\n")
        token_count = count_tokens(chunk_text)
        chunk_idx = len(chunks)
        chunk_id = f"{metadata.file_name}:{metadata.title[:50]}:chunk_{chunk_idx}"
        chunks.append(TextChunk(
            chunk_id=chunk_id,
            text=chunk_text,
            token_count=token_count,
            metadata=metadata.model_copy(update={"chunk_index": chunk_idx}),
        ))

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        # If a single sentence exceeds max, force-split by token count
        if sentence_tokens > max_tokens:
            _flush()
            for sub in _force_split_by_tokens(sentence, target_tokens):
                current_sentences = [sub]
                current_tokens = count_tokens(sub)
                _flush()
            current_sentences = []
            current_tokens = 0
            continue

        # If adding this sentence would exceed max, flush
        if current_tokens + sentence_tokens > max_tokens and current_tokens >= min_tokens:
            _flush()
            # Overlap: carry over last sentences up to overlap_tokens
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

    # Flush remaining
    _flush()

    # Update total_chunks in all chunk metadata
    total = len(chunks)
    for chunk in chunks:
        chunk.metadata.total_chunks = total

    return chunks


_VALID_CHUNK_TYPES = {"rule", "exception", "definition", "threshold", "applicability", "general"}

_CLASSIFY_SYSTEM = (
    "You classify regulatory document chunks into exactly one category.\n"
    "Categories: rule, exception, definition, threshold, applicability, general\n"
    "- rule: mandatory obligations, directives, compliance requirements\n"
    "- exception: exemptions, carve-outs, exceptions to rules\n"
    "- definition: definitions of terms, acronyms, interpretations\n"
    "- threshold: numerical limits, percentages, monetary limits, ratios\n"
    "- applicability: who/what the regulation applies to, scope\n"
    "- general: everything else (introductions, references, misc)\n\n"
    "Input: JSON array of {id, preview}. Output: JSON array of {id, type}.\n"
    "Output ONLY valid JSON, no markdown fences."
)


def classify_chunks(chunks: list[TextChunk], llm) -> list[TextChunk]:
    """Classify chunks by type using an LLM. Falls back to 'general' on failure."""
    if not chunks:
        return chunks

    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        items = []
        for j, chunk in enumerate(batch):
            preview = chunk.text[:300]
            items.append({"id": j, "preview": preview})

        prompt = json.dumps(items)
        try:
            raw = llm.generate(prompt, system=_CLASSIFY_SYSTEM, max_tokens=500, temperature=0)
            # Strip markdown fences if present
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
                        batch[idx].metadata.chunk_type = ctype
        except Exception as e:
            print(f"Chunk classification batch failed (offset {i}): {e}")
            # Chunks keep default "general" type

    return chunks
