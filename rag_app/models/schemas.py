from pydantic import BaseModel, Field
from typing import Optional


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


class AskRequest(BaseModel):
    question: str
    top_k: int = Field(default=12, ge=1, le=20)
    source_filter: Optional[str] = None


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


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    query_used: str
    chunks_retrieved: int
    retrieved_chunks: list[RetrievedChunk] = []


# ── Eval schemas ──────────────────────────────────────────────


class EvalQuestion(BaseModel):
    question: str
    ground_truth: Optional[str] = None
    source_filter: Optional[str] = None


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
    vanilla_eval: SingleAnswerEval
    rag_sources: list[SourceReference]
    rag_advantage: float  # rag avg - vanilla avg


class EvalRequest(BaseModel):
    question: str
    ground_truth: Optional[str] = None
    source_filter: Optional[str] = None


class EvalResponse(BaseModel):
    result: QuestionEvalResult


class EvalSummary(BaseModel):
    total_questions: int
    rag_average: float
    vanilla_average: float
    rag_advantage: float
    per_criterion_rag: dict[str, float]
    per_criterion_vanilla: dict[str, float]
    wins: int  # questions where RAG scored higher
    losses: int  # questions where vanilla scored higher
    ties: int


class BatchEvalResponse(BaseModel):
    results: list[QuestionEvalResult]
    summary: EvalSummary
