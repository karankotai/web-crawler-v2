import re

from pydantic import BaseModel, Field, field_validator
from typing import Optional

VALID_SOURCES = {"rbi", "sebi", "mca", "irdai", "egazette", "cbic", "cbdt", "icai", "ibbi", "dgft", "legislation", "gst_council", "practitioner_knowledge", "other"}


class ChunkMetadata(BaseModel):
    source: str = ""
    title: str = ""
    date: str = ""
    link: str = ""
    circular_number: str = ""
    chunk_index: int = 0
    total_chunks: int = 0
    file_name: str = ""
    pdf_links: list[str] = []
    chunk_type: str = "general"  # rule, exception, definition, threshold, applicability, procedure, general
    topic: str = ""               # short subject label (e.g. "asset classification")
    section_index: int = 0        # which section (0-based) this chunk came from
    section_heading: str = ""     # raw heading text of the section
    context_summary: str = ""     # LLM-generated context blurb for embedding enrichment


class TextChunk(BaseModel):
    chunk_id: str
    text: str
    token_count: int
    metadata: ChunkMetadata


class IndexRequest(BaseModel):
    force_reindex: bool = False


class IndexResponse(BaseModel):
    total_records: int
    records_with_content: int
    total_chunks: int
    total_vectors_stored: int
    sources_indexed: list[str]
    duration_seconds: float
    skipped_records: int = 0
    new_records: int = 0


class AskRequest(BaseModel):
    question: str = Field(max_length=2000)
    top_k: int = Field(default=12, ge=1, le=20)
    source_filter: Optional[str | list[str]] = Field(default=None)
    multi_query: Optional[bool] = None  # None = use server default (MULTI_QUERY_ENABLED)

    @field_validator("source_filter")
    @classmethod
    def validate_source_filter(cls, v: str | list[str] | None) -> str | list[str] | None:
        if v is None:
            return v
        # Normalize single string to check, keep as-is for type
        sources = [v] if isinstance(v, str) else v
        for s in sources:
            if s.lower() not in VALID_SOURCES:
                raise ValueError(f"Invalid source '{s}'. Must be one of: {', '.join(sorted(VALID_SOURCES))}")
        return v


class SourceReference(BaseModel):
    title: str
    source: str
    date: str
    link: str
    circular_number: str
    relevance_score: float
    pdf_links: list[str] = []


class RetrievedChunk(BaseModel):
    text: str
    source: str
    title: str
    circular_number: str
    relevance_score: float
    chunk_type: str = "general"
    topic: str = ""


class GraphContext(BaseModel):
    amendment_chain: list[str] = []
    freshness_notes: dict[str, str] = {}
    related_circulars: list[str] = []
    impact_entities: list[str] = []
    graph_intent: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    query_used: str
    chunks_retrieved: int
    retrieved_chunks: list[RetrievedChunk] = []
    graph_context: Optional[GraphContext] = None


# ── Eval schemas ──────────────────────────────────────────────


class EvalQuestion(BaseModel):
    question: str = Field(max_length=2000)
    ground_truth: Optional[str] = Field(default=None, max_length=5000)
    source_filter: Optional[str] = Field(default=None, max_length=50)

    @field_validator("source_filter")
    @classmethod
    def validate_source_filter(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in VALID_SOURCES:
            raise ValueError(f"source_filter must be one of: {', '.join(sorted(VALID_SOURCES))}")
        return v


class CriterionScore(BaseModel):
    criterion: str
    score: int = Field(ge=1, le=5)
    reasoning: str


class SingleAnswerEval(BaseModel):
    answer: str
    scores: list[CriterionScore]
    total_score: int
    average_score: float


class QuestionEvalResult(BaseModel):
    question: str
    ground_truth: Optional[str] = None
    rag_eval: SingleAnswerEval
    vanilla_gpt_eval: Optional[SingleAnswerEval] = None
    vanilla_gemini_eval: Optional[SingleAnswerEval] = None
    custom_eval: Optional[SingleAnswerEval] = None
    rag_sources: list[SourceReference]
    rag_advantage_vs_gpt: Optional[float] = None
    rag_advantage_vs_gemini: Optional[float] = None
    rag_advantage_vs_custom: Optional[float] = None


class EvalRequest(BaseModel):
    question: str = Field(max_length=2000)
    ground_truth: Optional[str] = Field(default=None, max_length=5000)
    source_filter: Optional[str] = Field(default=None, max_length=50)
    baselines: list[str] = Field(default=["gpt", "gemini"])
    custom_answer: Optional[str] = Field(default=None, max_length=10000)

    @field_validator("source_filter")
    @classmethod
    def validate_source_filter(cls, v: str | None) -> str | None:
        if v is not None and v.lower() not in VALID_SOURCES:
            raise ValueError(f"source_filter must be one of: {', '.join(sorted(VALID_SOURCES))}")
        return v


class EvalResponse(BaseModel):
    result: QuestionEvalResult


class EvalSummary(BaseModel):
    total_questions: int
    rag_average: float
    vanilla_gpt_average: Optional[float] = None
    vanilla_gemini_average: Optional[float] = None
    vanilla_custom_average: Optional[float] = None
    rag_advantage_vs_gpt: Optional[float] = None
    rag_advantage_vs_gemini: Optional[float] = None
    rag_advantage_vs_custom: Optional[float] = None
    per_criterion_rag: dict[str, float]
    per_criterion_vanilla_gpt: Optional[dict[str, float]] = None
    per_criterion_vanilla_gemini: Optional[dict[str, float]] = None
    per_criterion_custom: Optional[dict[str, float]] = None
    wins_vs_gpt: Optional[int] = None
    losses_vs_gpt: Optional[int] = None
    ties_vs_gpt: Optional[int] = None
    wins_vs_gemini: Optional[int] = None
    losses_vs_gemini: Optional[int] = None
    ties_vs_gemini: Optional[int] = None
    wins_vs_custom: Optional[int] = None
    losses_vs_custom: Optional[int] = None
    ties_vs_custom: Optional[int] = None


class BatchEvalResponse(BaseModel):
    results: list[QuestionEvalResult]
    summary: EvalSummary


# ── Crawl schemas ─────────────────────────────────────────────


class UploadResponse(BaseModel):
    status: str
    documents_saved: int
    chunks_indexed: int
    message: str


class CrawlRequest(BaseModel):
    source: str = Field(
        default="all",
        description="Which source to crawl: rbi, sebi, mca, irdai, egazette, or all",
    )
    max_pages: int = Field(default=50, ge=1, le=500)
    deep_crawl: bool = False
    output_format: str = Field(default="both", pattern="^(json|csv|both)$")
    offset: int = Field(default=0, ge=0, le=10000)


class CrawlResponse(BaseModel):
    status: str
    task_id: str
    source: str
    message: str


# ── Analysis chat schemas ────────────────────────────────────


# ── Obligations schemas ─────────────────────────────────────


class ObligationExtractRequest(BaseModel):
    url: str = Field(max_length=2000)
    chain_type: Optional[str] = None
    repealed_by: Optional[str] = None


class ObligationExtractResponse(BaseModel):
    status: str
    obligation: dict


class ObligationListResponse(BaseModel):
    obligations: list[dict]
    page: int
    total_pages: int
    total: int


# ── Analysis chat schemas ────────────────────────────────────


class AnalysisChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=10000)


class AnalysisChatRequest(BaseModel):
    analysis_text: str = Field(min_length=50)
    question: str = Field(max_length=2000)
    history: list[AnalysisChatMessage] = Field(default=[])
